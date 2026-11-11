import base64
from flask import Blueprint, request, jsonify, current_app
from backend.middleware.auth import require_auth
from backend.middleware.errors import database_error_response
from backend.middleware.tenant import current_restaurant_id
from backend.services.supabase_client import supabase
from backend.services.money_engine import calculate_recipe_cost
from backend.services.menu_scanner import scan_menu_payload
from backend.services.validation import ValidationError, parse_finite_number, parse_nonempty_string

menu_bp = Blueprint("menu", __name__, url_prefix="/api/v1/menu")

MAX_INGREDIENTS = 200
MAX_BULK_ITEMS = 500
DESC_SEPARATOR = " :: "


def _bad_request(message):
    return jsonify({"success": False, "error": message, "code": "BAD_REQUEST"}), 400


def _not_found():
    # Same response whether the item does not exist or belongs to another restaurant.
    return jsonify({"success": False, "error": "Menu item not found", "code": "NOT_FOUND"}), 404


def _pack_name_and_description(name: str, description: str | None) -> str:
    """Pack dish name and optional description into menu_items.name (VARCHAR 255)."""
    clean_name = str(name or "").strip()
    clean_desc = str(description or "").strip()
    if not clean_desc:
        return clean_name[:255]
    combined = f"{clean_name}{DESC_SEPARATOR}{clean_desc}"
    return combined[:255]


def _enrich_menu_item(item: dict) -> dict:
    """Unpack description (if packed in name) and compute unit_margin and food_cost_pct."""
    raw_name = str(item.get("name") or "")
    if DESC_SEPARATOR in raw_name:
        clean_name, unpacked_desc = raw_name.split(DESC_SEPARATOR, 1)
        item["name"] = clean_name.strip()
        if not item.get("description"):
            item["description"] = unpacked_desc.strip()
    elif "description" not in item or item["description"] is None:
        item["description"] = ""

    price = float(item.get("selling_price") or item.get("price") or 0.0)
    cost = float(item.get("cost_price") or item.get("cost") or 0.0)
    item["selling_price"] = price
    item["cost_price"] = cost
    item["unit_margin"] = round(price - cost, 2)
    item["food_cost_pct"] = round((cost / price * 100), 1) if price > 0 else 0.0
    return item


def _fetch_owned_item(item_id, restaurant_id, columns="id, name, selling_price, cost_price"):
    """
    Return the menu item only if it belongs to `restaurant_id`, else None.
    Every recipe operation must call this BEFORE touching the recipes table.
    Raises on database failure (callers convert to a 5xx response).
    """
    res = (
        supabase.table("menu_items")
        .select(columns)
        .eq("id", item_id)
        .eq("restaurant_id", restaurant_id)
        .limit(1)
        .execute()
    )
    rows = res.data if res and isinstance(res.data, list) else []
    return rows[0] if rows else None


@menu_bp.route("/", methods=["GET"])
@require_auth
def list_menu_items():
    """
    GET /api/v1/menu
    List all menu items for the caller's restaurant with selling price, cost price, and active status.
    """
    restaurant_id = current_restaurant_id()

    try:
        res = (
            supabase.table("menu_items")
            .select("*")
            .eq("restaurant_id", restaurant_id)
            .order("category")
            .order("name")
            .execute()
        )
    except Exception as exc:
        return database_error_response(exc, "menu list")

    items = res.data if res and res.data else []
    for item in items:
        _enrich_menu_item(item)

    return jsonify({
        "success": True,
        "restaurant_id": restaurant_id,
        "count": len(items),
        "data": items
    }), 200


@menu_bp.route("/scan", methods=["POST"])
@require_auth
def scan_menu():
    """
    POST /api/v1/menu/scan
    Accepts an uploaded menu image (multipart/form-data or base64 JSON) and/or OCR text,
    extracts structured menu items, and returns them for editable review before saving.
    """
    restaurant_id = current_restaurant_id()
    image_bytes = None
    mime_type = "image/jpeg"
    ocr_text = None
    candidate_items = None
    expand_sizes = False

    if request.files:
        uploaded = request.files.get("image") or request.files.get("file")
        if uploaded:
            image_bytes = uploaded.read()
            mime_type = uploaded.mimetype or "image/jpeg"
        ocr_text = request.form.get("ocr_text")
        expand_sizes = str(request.form.get("expand_sizes") or "").lower() in ("true", "1", "yes")
    else:
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return _bad_request("Provide a menu image upload or JSON scan payload")

        ocr_text = payload.get("ocr_text")
        candidate_items = payload.get("items")
        expand_sizes = bool(payload.get("expand_sizes", False))
        mime_type = str(payload.get("mime_type") or "image/jpeg")

        b64_raw = payload.get("image_base64")
        if b64_raw and isinstance(b64_raw, str):
            if "," in b64_raw and b64_raw.strip().startswith("data:"):
                header, b64_raw = b64_raw.split(",", 1)
                if ":" in header and ";" in header:
                    mime_type = header.split(":", 1)[1].split(";", 1)[0]
            try:
                image_bytes = base64.b64decode(b64_raw)
            except Exception:
                return _bad_request("image_base64 is not valid base64 data")

    if not image_bytes and not (ocr_text and str(ocr_text).strip()) and not candidate_items:
        return _bad_request("Provide an image file, image_base64, or ocr_text to scan")

    scan_result = scan_menu_payload(
        image_bytes=image_bytes,
        mime_type=mime_type,
        ocr_text=ocr_text,
        candidate_items=candidate_items,
        expand_sizes=expand_sizes,
    )

    return jsonify({
        "success": True,
        "restaurant_id": restaurant_id,
        "source": scan_result["source"],
        "count": scan_result["count"],
        "items": scan_result["items"],
    }), 200


@menu_bp.route("/bulk", methods=["POST"])
@require_auth
def bulk_create_menu_items():
    """
    POST /api/v1/menu/bulk
    Save multiple verified menu items from the Menu Scan review screen in a single batch,
    always stamped with the authenticated caller's restaurant_id.
    """
    restaurant_id = current_restaurant_id()
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
        return _bad_request("Request body must be a JSON object with an 'items' list")

    raw_items = payload["items"]
    if not raw_items:
        return _bad_request("items list must contain at least one menu item")
    if len(raw_items) > MAX_BULK_ITEMS:
        return _bad_request(f"Cannot import more than {MAX_BULK_ITEMS} items per batch")

    records = []
    for idx, item in enumerate(raw_items):
        label = f"items[{idx}]"
        if not isinstance(item, dict):
            return _bad_request(f"{label} must be an object")

        price_raw = item.get("selling_price") if item.get("selling_price") is not None else item.get("price")
        cost_raw = item.get("cost_price") if item.get("cost_price") is not None else item.get("cost", 0.0)
        if not item.get("name") or price_raw is None:
            return _bad_request(f"{label} is missing required fields: name and selling_price")

        try:
            name = parse_nonempty_string(item.get("name"), f"{label}.name")
            price = parse_finite_number(price_raw, f"{label}.selling_price", min_value=0)
            cost = parse_finite_number(cost_raw, f"{label}.cost_price", min_value=0)
        except ValidationError as exc:
            return _bad_request(str(exc))

        category = str(item.get("category") or "General").strip() or "General"
        description = item.get("description")
        packed_name = _pack_name_and_description(name, description)

        records.append({
            "restaurant_id": restaurant_id,
            "name": packed_name,
            "category": category,
            "selling_price": price,
            "price": price,
            "cost_price": cost,
            "cost": cost,
            "is_active": bool(item.get("is_active", True)),
        })

    try:
        res = supabase.table("menu_items").insert(records).execute()
    except Exception as exc:
        return database_error_response(exc, "bulk menu item insert")

    inserted = res.data if res and isinstance(res.data, list) else []
    if not inserted:
        return database_error_response(
            RuntimeError("bulk menu item insert returned no rows"),
            "bulk menu item insert",
        )

    for row in inserted:
        _enrich_menu_item(row)

    return jsonify({
        "success": True,
        "restaurant_id": restaurant_id,
        "inserted_count": len(inserted),
        "data": inserted,
    }), 201


@menu_bp.route("/", methods=["POST"])
@require_auth
def create_menu_item():
    """
    POST /api/v1/menu
    Create a new menu item for the caller's restaurant (restaurant_id is never taken from the payload).
    """
    restaurant_id = current_restaurant_id()
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return _bad_request("Request body must be a JSON object")

    price = data.get("selling_price") if data.get("selling_price") is not None else data.get("price")
    cost = data.get("cost_price") if data.get("cost_price") is not None else data.get("cost", 0.0)

    if not data.get("name") or price is None:
        return _bad_request("Missing required fields: name and selling_price")

    try:
        name = parse_nonempty_string(data.get("name"), "name")
        price = parse_finite_number(price, "selling_price", min_value=0)
        cost = parse_finite_number(cost, "cost_price", min_value=0)
    except ValidationError as exc:
        return _bad_request(str(exc))

    packed_name = _pack_name_and_description(name, data.get("description"))

    record = {
        "restaurant_id": restaurant_id,
        "name": packed_name,
        "category": data.get("category", "General"),
        "selling_price": price,
        "price": price,
        "cost_price": cost,
        "cost": cost,
        "is_active": bool(data.get("is_active", True))
    }

    try:
        res = supabase.table("menu_items").insert(record).execute()
    except Exception as exc:
        return database_error_response(exc, "menu item insert")

    if not res or not res.data:
        return database_error_response(RuntimeError("menu item insert returned no rows"), "menu item insert")

    created_row = _enrich_menu_item(dict(res.data[0]))
    return jsonify({"success": True, "data": created_row}), 201


@menu_bp.route("/<item_id>", methods=["PUT"])
@require_auth
def update_menu_item(item_id):
    """
    PUT /api/v1/menu/<item_id>
    Update pricing, category, name, description, or active status for one of the caller's menu items.
    """
    restaurant_id = current_restaurant_id()
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return _bad_request("Request body must be a JSON object")

    updates = {}
    try:
        if "name" in data:
            clean_name = parse_nonempty_string(data["name"], "name")
            if "description" in data:
                updates["name"] = _pack_name_and_description(clean_name, data.get("description"))
            else:
                updates["name"] = clean_name
        elif "description" in data:
            existing_res = (
                supabase.table("menu_items")
                .select("name")
                .eq("id", item_id)
                .eq("restaurant_id", restaurant_id)
                .limit(1)
                .execute()
            )
            if not existing_res or not existing_res.data:
                return _not_found()
            base_name, _ = _unpack_name_and_description(existing_res.data[0].get("name", ""))
            updates["name"] = _pack_name_and_description(base_name, data.get("description"))
        if "category" in data:
            updates["category"] = data["category"]
        if "is_active" in data:
            updates["is_active"] = bool(data["is_active"])

        price_val = data.get("selling_price") if "selling_price" in data else data.get("price")
        if price_val is not None:
            p = parse_finite_number(price_val, "selling_price", min_value=0)
            updates["selling_price"] = p
            updates["price"] = p

        cost_val = data.get("cost_price") if "cost_price" in data else data.get("cost")
        if cost_val is not None:
            c = parse_finite_number(cost_val, "cost_price", min_value=0)
            updates["cost_price"] = c
            updates["cost"] = c
    except ValidationError as exc:
        return _bad_request(str(exc))

    if not updates:
        return _bad_request("No update fields provided")

    try:
        res = (
            supabase.table("menu_items")
            .update(updates)
            .eq("id", item_id)
            .eq("restaurant_id", restaurant_id)
            .execute()
        )
    except Exception as exc:
        return database_error_response(exc, "menu item update")

    if not res or not res.data:
        return _not_found()

    updated_row = _enrich_menu_item(dict(res.data[0]))
    return jsonify({"success": True, "data": updated_row}), 200


@menu_bp.route("/<item_id>", methods=["DELETE"])
@require_auth
def delete_menu_item(item_id):
    """
    DELETE /api/v1/menu/<item_id>
    Soft-delete/archive one of the caller's menu items by marking is_active = False,
    or permanently delete when ?permanent=true is specified.
    """
    restaurant_id = current_restaurant_id()
    permanent = str(request.args.get("permanent") or "").lower() in ("true", "1", "yes")

    try:
        if permanent:
            res = (
                supabase.table("menu_items")
                .delete()
                .eq("id", item_id)
                .eq("restaurant_id", restaurant_id)
                .execute()
            )
        else:
            res = (
                supabase.table("menu_items")
                .update({"is_active": False})
                .eq("id", item_id)
                .eq("restaurant_id", restaurant_id)
                .execute()
            )
    except Exception as exc:
        return database_error_response(exc, "menu item archive")

    if not res or not res.data:
        return _not_found()

    return jsonify({
        "success": True,
        "message": f"Menu item {item_id} {'deleted' if permanent else 'archived'} successfully",
        "item_id": item_id
    }), 200


@menu_bp.route("/<item_id>/recipe", methods=["GET"])
@require_auth
def get_item_recipe(item_id):
    """
    GET /api/v1/menu/<item_id>/recipe
    Retrieve bill of materials and calculated portion food cost.
    Ownership of the menu item is verified before any recipe row is read.
    """
    restaurant_id = current_restaurant_id()

    try:
        menu_item = _fetch_owned_item(item_id, restaurant_id)
        if menu_item is None:
            return _not_found()
        recipe_res = supabase.table("recipes").select("*").eq("menu_item_id", item_id).execute()
    except Exception as exc:
        return database_error_response(exc, "recipe read")

    ingredients = recipe_res.data if recipe_res and recipe_res.data else []

    return jsonify({
        "success": True,
        "menu_item_id": item_id,
        "menu_item": menu_item,
        "ingredients": ingredients,
        "calculated_recipe_cost": calculate_recipe_cost(ingredients)
    }), 200


def _validate_ingredients(ingredients, item_id):
    """Validate every ingredient strictly; raises ValidationError instead of silently skipping."""
    if len(ingredients) > MAX_INGREDIENTS:
        raise ValidationError(f"A recipe can have at most {MAX_INGREDIENTS} ingredients")
    records = []
    for index, ing in enumerate(ingredients, start=1):
        if not isinstance(ing, dict):
            raise ValidationError(f"Ingredient #{index} must be an object")
        label = f"Ingredient #{index}"
        records.append({
            "menu_item_id": item_id,
            "ingredient_name": parse_nonempty_string(ing.get("ingredient_name"), f"{label} ingredient_name"),
            "quantity": parse_finite_number(ing.get("quantity"), f"{label} quantity", min_value=0.001),
            "unit": parse_nonempty_string(ing.get("unit", "portion"), f"{label} unit", max_length=50),
            "unit_cost": parse_finite_number(ing.get("unit_cost"), f"{label} unit_cost", min_value=0)
        })
    return records


@menu_bp.route("/<item_id>/recipe", methods=["POST"])
@require_auth
def upsert_item_recipe(item_id):
    """
    POST /api/v1/menu/<item_id>/recipe
    Replace recipe ingredients for one of the caller's menu items and recalculate cost_price.

    Ownership is verified first. New rows are inserted BEFORE old rows are removed, and
    new rows are rolled back if removing the old ones fails, so a failure never leaves
    the item without its previous recipe.
    """
    restaurant_id = current_restaurant_id()
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or not isinstance(payload.get("ingredients"), list):
        return _bad_request("Payload must include an 'ingredients' list")

    # 1. Ownership first: nothing below runs for another restaurant's item
    try:
        owned_item = _fetch_owned_item(item_id, restaurant_id)
    except Exception as exc:
        return database_error_response(exc, "recipe ownership check")
    if owned_item is None:
        return _not_found()

    # 2. Validate input and compute cost from the validated ingredients only
    try:
        records = _validate_ingredients(payload["ingredients"], item_id)
    except ValidationError as exc:
        return _bad_request(str(exc))
    calculated_cost = calculate_recipe_cost(records)

    # 3. Replace recipe rows (insert new -> delete old, rollback new on failure)
    try:
        old_res = supabase.table("recipes").select("id").eq("menu_item_id", item_id).execute()
        old_ids = [
            r["id"] for r in (old_res.data if old_res and old_res.data else [])
            if isinstance(r, dict) and r.get("id") is not None
        ]

        inserted_recipes = []
        if records:
            ins_res = supabase.table("recipes").insert(records).execute()
            inserted_recipes = ins_res.data if ins_res and ins_res.data else []
            if not inserted_recipes:
                raise RuntimeError("recipe insert returned no rows")

        if old_ids:
            try:
                supabase.table("recipes").delete().in_("id", old_ids).execute()
            except Exception:
                new_ids = [r["id"] for r in inserted_recipes if isinstance(r, dict) and r.get("id") is not None]
                if new_ids:
                    try:
                        supabase.table("recipes").delete().in_("id", new_ids).execute()
                    except Exception as rollback_exc:
                        current_app.logger.error("Recipe rollback failed", exc_info=rollback_exc)
                raise

        # 4. Update plate cost, scoped to the caller's restaurant
        update_res = (
            supabase.table("menu_items")
            .update({"cost_price": calculated_cost, "cost": calculated_cost})
            .eq("id", item_id)
            .eq("restaurant_id", restaurant_id)
            .execute()
        )
    except Exception as exc:
        return database_error_response(exc, "recipe upsert")

    if not update_res or not update_res.data:
        return _not_found()

    return jsonify({
        "success": True,
        "menu_item_id": item_id,
        "calculated_cost_price": calculated_cost,
        "ingredients_count": len(inserted_recipes),
        "ingredients": inserted_recipes,
        "updated_menu_item": update_res.data[0]
    }), 201
