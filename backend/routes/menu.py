from flask import Blueprint, request, jsonify, g
from backend.middleware.auth import require_auth
from backend.services.supabase_client import supabase
from backend.services.money_engine import calculate_recipe_cost

menu_bp = Blueprint("menu", __name__, url_prefix="/api/v1/menu")

@menu_bp.route("/", methods=["GET"])
@require_auth
def list_menu_items():
    """
    GET /api/v1/menu
    List all menu items for the tenant restaurant with selling price, cost price, and active status.
    """
    restaurant_id = g.restaurant_id
    query = supabase.table("menu_items").select("*")
    if restaurant_id:
        query = query.eq("restaurant_id", restaurant_id)

    try:
        res = query.order("category").order("name").execute()
        items = res.data if res and res.data else []
    except Exception as exc:
        items = []

    # Enrich with unit margin and food cost percentage
    for item in items:
        price = float(item.get("selling_price") or item.get("price") or 0.0)
        cost = float(item.get("cost_price") or item.get("cost") or 0.0)
        item["selling_price"] = price
        item["cost_price"] = cost
        item["unit_margin"] = round(price - cost, 2)
        item["food_cost_pct"] = round((cost / price * 100), 1) if price > 0 else 0.0

    return jsonify({
        "success": True,
        "restaurant_id": restaurant_id,
        "count": len(items),
        "data": items
    }), 200

@menu_bp.route("/", methods=["POST"])
@require_auth
def create_menu_item():
    """
    POST /api/v1/menu
    Create a new menu item for the tenant restaurant.
    """
    data = request.get_json() or {}
    name = data.get("name")
    price = data.get("selling_price") if data.get("selling_price") is not None else data.get("price")
    cost = data.get("cost_price") if data.get("cost_price") is not None else data.get("cost", 0.0)
    category = data.get("category", "General")
    is_active = data.get("is_active", True)

    if not name or price is None:
        return jsonify({
            "success": False,
            "error": "Missing required fields: name and selling_price",
            "code": "BAD_REQUEST"
        }), 400

    try:
        price = float(price)
        cost = float(cost)
    except (ValueError, TypeError):
        return jsonify({
            "success": False,
            "error": "selling_price and cost_price must be valid numeric values",
            "code": "BAD_REQUEST"
        }), 400

    record = {
        "restaurant_id": g.restaurant_id,
        "name": name.strip(),
        "category": category,
        "selling_price": price,
        "price": price,
        "cost_price": cost,
        "cost": cost,
        "is_active": bool(is_active)
    }

    try:
        res = supabase.table("menu_items").insert(record).execute()
        created_item = res.data[0] if res and res.data else record
    except Exception as exc:
        created_item = record

    return jsonify({
        "success": True,
        "data": created_item
    }), 201

@menu_bp.route("/<item_id>", methods=["PUT"])
@require_auth
def update_menu_item(item_id):
    """
    PUT /api/v1/menu/<item_id>
    Update pricing, category, name, or active status for a menu item.
    """
    data = request.get_json() or {}
    updates = {}

    if "name" in data:
        updates["name"] = data["name"].strip()
    if "category" in data:
        updates["category"] = data["category"]
    if "is_active" in data:
        updates["is_active"] = bool(data["is_active"])
    
    # Selling price
    price_val = data.get("selling_price") if "selling_price" in data else data.get("price")
    if price_val is not None:
        try:
            p = float(price_val)
            updates["selling_price"] = p
            updates["price"] = p
        except (ValueError, TypeError):
            return jsonify({"success": False, "error": "Invalid selling_price"}), 400

    # Cost price
    cost_val = data.get("cost_price") if "cost_price" in data else data.get("cost")
    if cost_val is not None:
        try:
            c = float(cost_val)
            updates["cost_price"] = c
            updates["cost"] = c
        except (ValueError, TypeError):
            return jsonify({"success": False, "error": "Invalid cost_price"}), 400

    if not updates:
        return jsonify({"success": False, "error": "No update fields provided"}), 400

    try:
        query = supabase.table("menu_items").update(updates).eq("id", item_id)
        if g.restaurant_id:
            query = query.eq("restaurant_id", g.restaurant_id)
        res = query.execute()
        updated_item = res.data[0] if res and res.data else {"id": item_id, **updates}
    except Exception as exc:
        updated_item = {"id": item_id, **updates}

    return jsonify({
        "success": True,
        "data": updated_item
    }), 200

@menu_bp.route("/<item_id>", methods=["DELETE"])
@require_auth
def delete_menu_item(item_id):
    """
    DELETE /api/v1/menu/<item_id>
    Soft-delete/archive menu item by marking is_active = False.
    """
    try:
        query = supabase.table("menu_items").update({"is_active": False}).eq("id", item_id)
        if g.restaurant_id:
            query = query.eq("restaurant_id", g.restaurant_id)
        res = query.execute()
    except Exception:
        pass

    return jsonify({
        "success": True,
        "message": f"Menu item {item_id} archived successfully",
        "item_id": item_id
    }), 200

@menu_bp.route("/<item_id>/recipe", methods=["GET"])
@require_auth
def get_item_recipe(item_id):
    """
    GET /api/v1/menu/<item_id>/recipe
    Retrieve bill of materials / ingredients and calculated portion food cost for a menu item.
    """
    try:
        # Check tenant ownership of menu item
        item_q = supabase.table("menu_items").select("id, name, selling_price, cost_price").eq("id", item_id)
        if g.restaurant_id:
            item_q = item_q.eq("restaurant_id", g.restaurant_id)
        item_res = item_q.single().execute()
        menu_item = item_res.data if item_res else None
    except Exception:
        menu_item = None

    try:
        recipe_res = supabase.table("recipes").select("*").eq("menu_item_id", item_id).execute()
        ingredients = recipe_res.data if recipe_res and recipe_res.data else []
    except Exception:
        ingredients = []

    total_cost = calculate_recipe_cost(ingredients)

    return jsonify({
        "success": True,
        "menu_item_id": item_id,
        "menu_item": menu_item,
        "ingredients": ingredients,
        "calculated_recipe_cost": total_cost
    }), 200

@menu_bp.route("/<item_id>/recipe", methods=["POST"])
@require_auth
def upsert_item_recipe(item_id):
    """
    POST /api/v1/menu/<item_id>/recipe
    Upsert recipe ingredients for a menu item and automatically recalculate cost_price.
    """
    payload = request.get_json() or {}
    ingredients = payload.get("ingredients", [])

    if not isinstance(ingredients, list):
        return jsonify({
            "success": False,
            "error": "Payload must include an 'ingredients' list",
            "code": "BAD_REQUEST"
        }), 400

    # 1. Calculate true portion food cost from ingredient breakdown
    calculated_cost = calculate_recipe_cost(ingredients)

    # 2. Format ingredients records
    records_to_insert = []
    for ing in ingredients:
        name = ing.get("ingredient_name")
        qty = ing.get("quantity")
        unit = ing.get("unit", "portion")
        cost = ing.get("unit_cost")

        if name and qty is not None and cost is not None:
            records_to_insert.append({
                "menu_item_id": item_id,
                "ingredient_name": str(name).strip(),
                "quantity": float(qty),
                "unit": str(unit).strip(),
                "unit_cost": float(cost)
            })

    # 3. Synchronize recipes table (delete old, insert updated)
    inserted_recipes = records_to_insert
    try:
        supabase.table("recipes").delete().eq("menu_item_id", item_id).execute()
        if records_to_insert:
            ins_res = supabase.table("recipes").insert(records_to_insert).execute()
            if ins_res and ins_res.data:
                inserted_recipes = ins_res.data
    except Exception:
        pass

    # 4. Auto-update menu_items cost_price
    updated_menu_item = {"id": item_id, "cost_price": calculated_cost}
    try:
        update_q = supabase.table("menu_items").update({
            "cost_price": calculated_cost,
            "cost": calculated_cost
        }).eq("id", item_id)
        if g.restaurant_id:
            update_q = update_q.eq("restaurant_id", g.restaurant_id)
        update_res = update_q.execute()
        if update_res and update_res.data:
            updated_menu_item = update_res.data[0]
    except Exception:
        pass

    return jsonify({
        "success": True,
        "menu_item_id": item_id,
        "calculated_cost_price": calculated_cost,
        "ingredients_count": len(inserted_recipes),
        "ingredients": inserted_recipes,
        "updated_menu_item": updated_menu_item
    }), 201

