from datetime import date
from collections import defaultdict
from flask import Blueprint, request, jsonify
from backend.middleware.auth import require_auth
from backend.middleware.errors import database_error_response
from backend.middleware.tenant import current_restaurant_id
from backend.services.supabase_client import supabase
from backend.services.money_engine import calculate_prime_cost, calculate_menu_matrix
from backend.services.validation import ValidationError, parse_finite_number

engine_bp = Blueprint("engine", __name__, url_prefix="/api/v1")


def _bad_request(message):
    return jsonify({"success": False, "error": message, "code": "BAD_REQUEST"}), 400


@engine_bp.route("/daily-financials", methods=["GET"])
@require_auth
def get_daily_financials():
    """
    GET /api/v1/daily-financials
    Returns the most recent daily financial record and trailing history for the caller's restaurant.
    """
    restaurant_id = current_restaurant_id()

    try:
        res = (
            supabase.table("daily_financials")
            .select("*")
            .eq("restaurant_id", restaurant_id)
            .order("date", desc=True)
            .limit(7)
            .execute()
        )
    except Exception as exc:
        return database_error_response(exc, "daily_financials query")

    rows = res.data if res and isinstance(res.data, list) else []
    if not rows:
        empty_metrics = calculate_prime_cost(
            cogs=0.0, labor_cost=0.0, gross_sales=0.0, target_prime_cost_pct=60.0
        )
        return jsonify({
            "success": True,
            "restaurant_id": restaurant_id,
            "has_data": False,
            "data": empty_metrics,
            "history": []
        }), 200

    latest = rows[0]
    metrics = calculate_prime_cost(
        cogs=float(latest.get("cogs") or 0.0),
        labor_cost=float(latest.get("labor_cost") or 0.0),
        gross_sales=float(latest.get("gross_sales") or 0.0),
        target_prime_cost_pct=60.0
    )
    metrics["date"] = latest.get("date")

    return jsonify({
        "success": True,
        "restaurant_id": restaurant_id,
        "has_data": True,
        "data": metrics,
        "history": rows
    }), 200


@engine_bp.route("/daily-financials", methods=["POST"])
@require_auth
def save_daily_financials():
    """
    POST /api/v1/daily-financials
    Accepts gross_sales, cogs, labor_cost.
    Calculates prime cost metrics and saves to Supabase daily_financials table,
    always stamped with the authenticated caller's restaurant_id.
    """
    restaurant_id = current_restaurant_id()
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return _bad_request("Request body must be a JSON object")

    if any(payload.get(k) is None for k in ("gross_sales", "cogs", "labor_cost")):
        return _bad_request("Missing required fields: gross_sales, cogs, labor_cost")

    try:
        gross_sales = parse_finite_number(payload.get("gross_sales"), "gross_sales", min_value=0)
        cogs = parse_finite_number(payload.get("cogs"), "cogs", min_value=0)
        labor_cost = parse_finite_number(payload.get("labor_cost"), "labor_cost", min_value=0)
        target_prime_cost_pct = parse_finite_number(
            payload.get("target_prime_cost_pct", 60.0), "target_prime_cost_pct",
            min_value=0, max_value=100
        )
    except ValidationError as exc:
        return _bad_request(str(exc))

    if gross_sales <= 0:
        return _bad_request("gross_sales must be greater than 0 to calculate Prime Cost %")

    entry_date = payload.get("date") or date.today().isoformat()
    try:
        date.fromisoformat(str(entry_date))
    except ValueError:
        return _bad_request("date must be an ISO date (YYYY-MM-DD)")

    metrics = calculate_prime_cost(
        cogs=cogs,
        labor_cost=labor_cost,
        gross_sales=gross_sales,
        target_prime_cost_pct=target_prime_cost_pct
    )

    # restaurant_id always comes from the authenticated profile, never from the payload
    record = {
        "restaurant_id": restaurant_id,
        "date": str(entry_date),
        "gross_sales": metrics["gross_sales"],
        "cogs": metrics["cogs"],
        "labor_cost": metrics["labor_cost"],
        "prime_cost": metrics["prime_cost"],
        "prime_cost_pct": metrics["prime_cost_pct"],
        "status": metrics["status"]
    }

    try:
        res = supabase.table("daily_financials").insert(record).execute()
    except Exception as exc:
        return database_error_response(exc, "daily_financials insert")

    if not res or not res.data:
        return database_error_response(
            RuntimeError("daily_financials insert returned no rows"), "daily_financials insert"
        )

    return jsonify({
        "success": True,
        "metrics": metrics,
        "saved_record": res.data[0]
    }), 201


@engine_bp.route("/menu-matrix", methods=["GET"])
@require_auth
def get_menu_matrix():
    """
    GET /api/v1/menu-matrix
    Queries menu_items and item_sales_logs for the caller's restaurant only,
    calculates the 4-quadrant Kasavana-Smith Menu Matrix, and returns categorized JSON.
    """
    restaurant_id = current_restaurant_id()

    try:
        items_res = (
            supabase.table("menu_items")
            .select("id, name, category, price, cost")
            .eq("restaurant_id", restaurant_id)
            .execute()
        )
        sales_res = (
            supabase.table("item_sales_logs")
            .select("item_id, quantity")
            .eq("restaurant_id", restaurant_id)
            .execute()
        )
    except Exception as exc:
        return database_error_response(exc, "menu matrix query")

    raw_items = items_res.data if items_res and items_res.data else []
    raw_sales = sales_res.data if sales_res and sales_res.data else []

    volume_map = defaultdict(int)
    for log in raw_sales:
        item_id = log.get("item_id")
        if item_id:
            volume_map[item_id] += log.get("quantity") or 0

    items_data = []
    for item in raw_items:
        item_id = item.get("id")
        raw_name = str(item.get("name", "Unnamed Item") or "Unnamed Item")
        clean_name = raw_name.split(" :: ", 1)[0].strip() if " :: " in raw_name else raw_name
        items_data.append({
            "id": item_id,
            "name": clean_name,
            "category": item.get("category", "General"),
            "price": item.get("price", 0.0),
            "cost": item.get("cost", 0.0),
            "volume": volume_map.get(item_id, 0)
        })

    return jsonify({
        "success": True,
        "restaurant_id": restaurant_id,
        "data": calculate_menu_matrix(items_data)
    }), 200
