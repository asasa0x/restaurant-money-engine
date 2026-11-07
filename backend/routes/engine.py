from datetime import date
from collections import defaultdict
from flask import Blueprint, request, jsonify, g
from backend.middleware.auth import require_auth
from backend.services.supabase_client import supabase
from backend.services.money_engine import calculate_prime_cost, calculate_menu_matrix

engine_bp = Blueprint("engine", __name__, url_prefix="/api/v1")

@engine_bp.route("/daily-financials", methods=["POST"])
@require_auth
def save_daily_financials():
    """
    POST /api/v1/daily-financials
    Accepts gross_sales, cogs, labor_cost.
    Calculates prime cost metrics and saves to Supabase daily_financials table.
    """
    payload = request.get_json() or {}
    
    # Extract financial inputs
    gross_sales = payload.get("gross_sales")
    cogs = payload.get("cogs")
    labor_cost = payload.get("labor_cost")
    target_prime_cost_pct = float(payload.get("target_prime_cost_pct", 60.0))
    entry_date = payload.get("date", date.today().isoformat())

    if gross_sales is None or cogs is None or labor_cost is None:
        return jsonify({
            "success": False,
            "error": "Missing required fields: gross_sales, cogs, labor_cost",
            "code": "BAD_REQUEST"
        }), 400

    try:
        gross_sales = float(gross_sales)
        cogs = float(cogs)
        labor_cost = float(labor_cost)
    except (ValueError, TypeError):
        return jsonify({
            "success": False,
            "error": "gross_sales, cogs, and labor_cost must be valid numbers",
            "code": "BAD_REQUEST"
        }), 400

    # Calculate Prime Cost metrics
    metrics = calculate_prime_cost(
        cogs=cogs,
        labor_cost=labor_cost,
        gross_sales=gross_sales,
        target_prime_cost_pct=target_prime_cost_pct
    )

    # Persist to Supabase daily_financials table
    record = {
        "restaurant_id": g.restaurant_id,
        "date": entry_date,
        "gross_sales": metrics["gross_sales"],
        "cogs": metrics["cogs"],
        "labor_cost": metrics["labor_cost"],
        "prime_cost": metrics["prime_cost"],
        "prime_cost_pct": metrics["prime_cost_pct"],
        "status": metrics["status"]
    }

    supabase_error = None
    saved_data = record

    try:
        res = supabase.table("daily_financials").insert(record).execute()
        if res and res.data:
            saved_data = res.data[0]
    except Exception as exc:
        supabase_error = str(exc)

    return jsonify({
        "success": True,
        "metrics": metrics,
        "saved_record": saved_data,
        "supabase_note": "Record persisted" if not supabase_error else f"Calculation succeeded, database write warning: {supabase_error}"
    }), 201

@engine_bp.route("/menu-matrix", methods=["GET"])
@require_auth
def get_menu_matrix():
    """
    GET /api/v1/menu-matrix
    Queries menu_items and item_sales_logs for g.restaurant_id,
    calculates the 4-quadrant Kasavana-Smith Menu Matrix, and returns categorized JSON.
    """
    restaurant_id = g.restaurant_id
    items_data = []

    try:
        # 1. Query menu items for the tenant restaurant
        items_query = supabase.table("menu_items").select("id, name, category, price, cost")
        if restaurant_id:
            items_query = items_query.eq("restaurant_id", restaurant_id)
        items_res = items_query.execute()
        raw_items = items_res.data if items_res and items_res.data else []

        # 2. Query item sales logs to aggregate volume sold
        sales_query = supabase.table("item_sales_logs").select("item_id, quantity")
        if restaurant_id:
            sales_query = sales_query.eq("restaurant_id", restaurant_id)
        sales_res = sales_query.execute()
        raw_sales = sales_res.data if sales_res and sales_res.data else []

        volume_map = defaultdict(int)
        for log in raw_sales:
            item_id = log.get("item_id")
            qty = log.get("quantity", 0)
            if item_id:
                volume_map[item_id] += qty

        # Combine menu items with aggregate sales volume
        for item in raw_items:
            item_id = item.get("id")
            items_data.append({
                "id": item_id,
                "name": item.get("name", "Unnamed Item"),
                "category": item.get("category", "General"),
                "price": item.get("price", 0.0),
                "cost": item.get("cost", 0.0),
                "volume": volume_map.get(item_id, 0)
            })

    except Exception:
        # In case tables do not exist yet or connection is offline, return empty matrix structure
        items_data = []

    # Calculate Kasavana-Smith Matrix
    matrix_result = calculate_menu_matrix(items_data)

    return jsonify({
        "success": True,
        "restaurant_id": restaurant_id,
        "data": matrix_result
    }), 200

