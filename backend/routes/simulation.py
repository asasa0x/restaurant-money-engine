from flask import Blueprint, request, jsonify, g
from backend.middleware.auth import require_auth
from backend.services.supabase_client import supabase
from backend.services.money_engine import simulate_profit_impact

simulation_bp = Blueprint("simulation", __name__, url_prefix="/api/v1/simulation")

@simulation_bp.route("/run", methods=["POST"])
@require_auth
def run_profit_simulation():
    """
    POST /api/v1/simulation/run
    Accepts:
    - ingredient_inflation_pct (or inflation_pct)
    - price_change_pct (or menu_markup_pct)
    - labor_change_pct (or labor_adjustment_pct)
    - optional baseline_financials { gross_sales, cogs, labor_cost }
    
    Runs what-if simulation against recent daily_financials and returns projected margins and deltas.
    """
    payload = request.get_json() or {}

    inflation_pct = float(
        payload.get("ingredient_inflation_pct")
        if payload.get("ingredient_inflation_pct") is not None
        else payload.get("inflation_pct", 0.0)
    )
    price_pct = float(
        payload.get("price_change_pct")
        if payload.get("price_change_pct") is not None
        else payload.get("menu_markup_pct", 0.0)
    )
    labor_pct = float(
        payload.get("labor_change_pct")
        if payload.get("labor_change_pct") is not None
        else payload.get("labor_adjustment_pct", 0.0)
    )

    # 1. Determine baseline financials: from payload or query recent daily_financials
    baseline = payload.get("baseline_financials")

    if not baseline or not isinstance(baseline, dict) or not baseline.get("gross_sales"):
        # Query recent daily_financials from Supabase for tenant
        restaurant_id = g.restaurant_id
        gross_sales = 0.0
        cogs = 0.0
        labor_cost = 0.0

        try:
            q = supabase.table("daily_financials").select("gross_sales, cogs, labor_cost")
            if restaurant_id:
                q = q.eq("restaurant_id", restaurant_id)
            res = q.order("date", desc=True).limit(30).execute()
            rows = res.data if res and res.data else []

            if rows:
                gross_sales = sum(float(r.get("gross_sales") or 0.0) for r in rows)
                cogs = sum(float(r.get("cogs") or 0.0) for r in rows)
                labor_cost = sum(float(r.get("labor_cost") or 0.0) for r in rows)
        except Exception:
            pass

        # If database has no entries yet, default to realistic baseline figures
        if gross_sales == 0:
            gross_sales = float(payload.get("gross_sales", 50000.0))
            cogs = float(payload.get("cogs", 15000.0))
            labor_cost = float(payload.get("labor_cost", 16000.0))

        baseline = {
            "gross_sales": gross_sales,
            "cogs": cogs,
            "labor_cost": labor_cost
        }

    # 2. Run simulation engine calculation
    sim_result = simulate_profit_impact(
        current_financials=baseline,
        ingredient_inflation_pct=inflation_pct,
        price_change_pct=price_pct,
        labor_change_pct=labor_pct
    )

    return jsonify({
        "success": True,
        "restaurant_id": g.restaurant_id,
        "simulation": sim_result
    }), 200

