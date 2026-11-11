from flask import Blueprint, request, jsonify
from backend.middleware.auth import require_auth
from backend.middleware.errors import database_error_response
from backend.middleware.tenant import current_restaurant_id
from backend.services.supabase_client import supabase
from backend.services.money_engine import simulate_profit_impact
from backend.services.validation import ValidationError, parse_finite_number

simulation_bp = Blueprint("simulation", __name__, url_prefix="/api/v1/simulation")


def _bad_request(message):
    return jsonify({"success": False, "error": message, "code": "BAD_REQUEST"}), 400


def _pct(payload, primary, alias):
    value = payload.get(primary)
    if value is None:
        value = payload.get(alias, 0.0)
    return parse_finite_number(value, primary, min_value=-100, max_value=1000)


@simulation_bp.route("/run", methods=["POST"])
@require_auth
def run_profit_simulation():
    """
    POST /api/v1/simulation/run
    Accepts:
    - ingredient_inflation_pct (or inflation_pct)
    - price_change_pct (or menu_markup_pct)
    - labor_change_pct (or labor_adjustment_pct)
    - optional baseline_financials { gross_sales, cogs, labor_cost } (explicit what-if baseline)

    Without an explicit baseline, uses the caller's own recent daily_financials.
    If the restaurant has no financial records, responds 422 instead of inventing numbers.
    """
    restaurant_id = current_restaurant_id()
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return _bad_request("Request body must be a JSON object")

    try:
        inflation_pct = _pct(payload, "ingredient_inflation_pct", "inflation_pct")
        price_pct = _pct(payload, "price_change_pct", "menu_markup_pct")
        labor_pct = _pct(payload, "labor_change_pct", "labor_adjustment_pct")

        baseline = payload.get("baseline_financials")
        if isinstance(baseline, dict) and baseline.get("gross_sales"):
            baseline = {
                key: parse_finite_number(baseline.get(key), f"baseline_financials.{key}", min_value=0)
                for key in ("gross_sales", "cogs", "labor_cost")
            }
        else:
            baseline = None
    except ValidationError as exc:
        return _bad_request(str(exc))

    if baseline is None:
        try:
            res = (
                supabase.table("daily_financials")
                .select("gross_sales, cogs, labor_cost")
                .eq("restaurant_id", restaurant_id)
                .order("date", desc=True)
                .limit(30)
                .execute()
            )
        except Exception as exc:
            return database_error_response(exc, "simulation baseline query")

        rows = res.data if res and res.data else []
        gross_sales = sum(float(r.get("gross_sales") or 0.0) for r in rows)
        if not rows or gross_sales <= 0:
            return jsonify({
                "success": False,
                "error": "No daily financial records found for this restaurant. "
                         "Log daily financials or provide baseline_financials.",
                "code": "NO_BASELINE_DATA"
            }), 422

        baseline = {
            "gross_sales": gross_sales,
            "cogs": sum(float(r.get("cogs") or 0.0) for r in rows),
            "labor_cost": sum(float(r.get("labor_cost") or 0.0) for r in rows)
        }

    sim_result = simulate_profit_impact(
        current_financials=baseline,
        ingredient_inflation_pct=inflation_pct,
        price_change_pct=price_pct,
        labor_change_pct=labor_pct
    )

    return jsonify({
        "success": True,
        "restaurant_id": restaurant_id,
        "simulation": sim_result
    }), 200
