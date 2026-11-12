"""
Customer QR ordering.

Public (no login) endpoints let a diner open a restaurant's menu from a QR code and place an
order. The server NEVER trusts client prices or restaurant data: every line is re-priced from
the database, limited to active items of the QR's restaurant, and the public menu never exposes
cost/margin data.

Authenticated owner endpoints (tenant-scoped) list orders and move them through the kitchen flow.
"""
import threading
import time
import uuid
from collections import defaultdict, deque

from flask import Blueprint, jsonify, request

from backend.middleware.auth import require_auth
from backend.middleware.errors import database_error_response
from backend.middleware.tenant import current_restaurant_id
from backend.services.supabase_client import supabase

public_bp = Blueprint("public_ordering", __name__, url_prefix="/api/v1/public")
orders_bp = Blueprint("orders", __name__, url_prefix="/api/v1/orders")

DESC_SEPARATOR = " :: "
ORDER_STATUSES = ("pending", "accepted", "preparing", "ready", "completed", "cancelled")
PAYMENT_METHODS = ("cash", "card", "easypaisa_jazzcash", "bank_transfer")
PAYMENT_PREFIX = "[Pay:"
MAX_LINES = 50
MAX_QTY = 50
MAX_LIST_LIMIT = 200

# Basic per-IP throttle for the public order endpoint (per server instance; a spam deterrent,
# not a substitute for edge/WAF rate limiting).
ORDER_RATE_LIMIT = 15
ORDER_RATE_WINDOW_SECONDS = 600
_rate_lock = threading.Lock()
_recent_orders = defaultdict(deque)


def _error(message, code, status):
    return jsonify({"success": False, "error": message, "code": code}), status


def _valid_uuid(value):
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, AttributeError, TypeError):
        return None


def _rate_limited(client_ip):
    now = time.monotonic()
    with _rate_lock:
        window = _recent_orders[client_ip]
        while window and now - window[0] > ORDER_RATE_WINDOW_SECONDS:
            window.popleft()
        if len(window) >= ORDER_RATE_LIMIT:
            return True
        window.append(now)
        return False


def _client_ip():
    forwarded = request.headers.get("X-Forwarded-For", "")
    return (forwarded.split(",")[0].strip() if forwarded else request.remote_addr) or "unknown"


def _split_name(raw_name):
    raw = str(raw_name or "")
    if DESC_SEPARATOR in raw:
        name, desc = raw.split(DESC_SEPARATOR, 1)
        return name.strip(), desc.strip()
    return raw.strip(), ""


PAYMENT_DETAIL_FIELDS = (
    ("bank_name", 100),
    ("account_title", 120),
    ("account_number", 60),
    ("iban", 60),
    ("wallet_provider", 60),
    ("wallet_number", 40),
    ("wallet_title", 120),
    ("instructions", 240),
)


def _clean_payment_ref(value):
    cleaned = _clean_text(value, "payment_ref", 60)
    if not cleaned:
        return None
    cleaned = cleaned.replace("[", "").replace("]", "").replace("|", "").strip()
    return cleaned or None


def _clean_payment_details(raw):
    if not isinstance(raw, dict):
        return {}
    out = {}
    for key, max_len in PAYMENT_DETAIL_FIELDS:
        val = raw.get(key)
        if isinstance(val, str):
            val = " ".join(val.split())[:max_len]
            if val:
                out[key] = val
    return out


def _pack_payment_and_notes(payment_method, notes, payment_ref=None):
    method = payment_method if payment_method in PAYMENT_METHODS else "cash"
    clean_notes = (notes or "").strip()
    ref = (payment_ref or "").replace("[", "").replace("]", "").replace("|", "").strip()[:60]
    tag = f"{method}|Ref:{ref}" if ref else method
    prefix = f"{PAYMENT_PREFIX}{tag}]"
    if not clean_notes:
        return prefix
    return f"{prefix} {clean_notes}"[:500]


def _unpack_payment_and_notes(raw_notes):
    text = str(raw_notes or "").strip()
    if text.startswith(PAYMENT_PREFIX) and "]" in text:
        end = text.index("]")
        tag = text[len(PAYMENT_PREFIX):end].strip()
        clean_notes = text[end + 1:].strip() or None
        method_part = tag
        payment_ref = None
        if "|Ref:" in tag:
            method_part, ref_part = tag.split("|Ref:", 1)
            method_part = method_part.strip()
            payment_ref = ref_part.strip() or None
        if method_part in PAYMENT_METHODS:
            return method_part, payment_ref, clean_notes
    return "cash", None, (text or None)


def _order_code(order_id):
    return str(order_id).replace("-", "")[:8].upper()


def _clean_text(value, field, max_length, required=False):
    if value is None or value == "":
        if required:
            raise ValueError(f"{field} is required")
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field} must be text")
    value = " ".join(value.split())
    if required and not value:
        raise ValueError(f"{field} is required")
    if len(value) > max_length:
        raise ValueError(f"{field} must be at most {max_length} characters")
    return value or None


def _fetch_restaurant(restaurant_id):
    try:
        res = (
            supabase.table("restaurants")
            .select("id, name, currency, payment_details")
            .eq("id", restaurant_id)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        if "payment_details" in str(exc) or "42703" in str(exc):
            res = (
                supabase.table("restaurants")
                .select("id, name, currency")
                .eq("id", restaurant_id)
                .limit(1)
                .execute()
            )
        else:
            raise
    rows = res.data if res and isinstance(res.data, list) else []
    return rows[0] if rows else None


# ---------------------------------------------------------------------------
# Public: QR menu + place order + track order
# ---------------------------------------------------------------------------
@public_bp.route("/restaurants/<restaurant_id>/menu", methods=["GET"])
def public_menu(restaurant_id):
    rid = _valid_uuid(restaurant_id)
    if not rid:
        return _error("Restaurant not found", "NOT_FOUND", 404)

    try:
        restaurant = _fetch_restaurant(rid)
        if not restaurant:
            return _error("Restaurant not found", "NOT_FOUND", 404)
        res = (
            supabase.table("menu_items")
            .select("id, name, category, selling_price, price")
            .eq("restaurant_id", rid)
            .eq("is_active", True)
            .order("category")
            .order("name")
            .execute()
        )
    except Exception as exc:
        return database_error_response(exc, "public menu read")

    items = []
    for row in (res.data if res and res.data else []):
        name, description = _split_name(row.get("name"))
        price = float(row.get("selling_price") or row.get("price") or 0)
        if not name or price <= 0:
            continue
        items.append({
            "id": row["id"],
            "name": name,
            "description": description,
            "category": row.get("category") or "General",
            "price": price,
        })

    return jsonify({
        "success": True,
        "restaurant": {
            "id": restaurant["id"],
            "name": restaurant.get("name"),
            "currency": restaurant.get("currency") or "USD",
            "payment_details": _clean_payment_details(restaurant.get("payment_details")),
        },
        "count": len(items),
        "items": items,
    }), 200


@public_bp.route("/restaurants/<restaurant_id>/orders", methods=["POST"])
def place_order(restaurant_id):
    rid = _valid_uuid(restaurant_id)
    if not rid:
        return _error("Restaurant not found", "NOT_FOUND", 404)

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return _error("Request body must be a JSON object", "BAD_REQUEST", 400)

    # --- validate customer details ---
    try:
        customer_name = _clean_text(payload.get("customer_name"), "Your name", 100, required=True)
        table_number = _clean_text(payload.get("table_number"), "Table number", 30)
        customer_phone = _clean_text(payload.get("customer_phone"), "Phone number", 30)
        notes = _clean_text(payload.get("notes"), "Notes", 450)
    except ValueError as exc:
        return _error(str(exc), "BAD_REQUEST", 400)

    raw_payment = payload.get("payment_method")
    if raw_payment is None or raw_payment == "":
        payment_method = "cash"
    elif not isinstance(raw_payment, str) or raw_payment.strip().lower() not in PAYMENT_METHODS:
        return _error(
            f"payment_method must be one of: {', '.join(PAYMENT_METHODS)}",
            "BAD_REQUEST",
            400,
        )
    else:
        payment_method = raw_payment.strip().lower()

    try:
        payment_ref = _clean_payment_ref(payload.get("payment_ref"))
    except ValueError as exc:
        return _error(str(exc), "BAD_REQUEST", 400)

    if not table_number and not customer_phone:
        return _error("Provide a table number or a phone number so the restaurant can reach you",
                      "BAD_REQUEST", 400)

    # --- validate cart lines (merge duplicates) ---
    raw_lines = payload.get("items")
    if not isinstance(raw_lines, list) or not raw_lines:
        return _error("Your cart is empty", "BAD_REQUEST", 400)
    if len(raw_lines) > MAX_LINES:
        return _error(f"An order can contain at most {MAX_LINES} different items", "BAD_REQUEST", 400)

    quantities = {}
    for line in raw_lines:
        if not isinstance(line, dict):
            return _error("Invalid cart item", "BAD_REQUEST", 400)
        item_id = _valid_uuid(line.get("menu_item_id"))
        qty = line.get("quantity")
        if not item_id:
            return _error("Invalid menu item in cart", "BAD_REQUEST", 400)
        if isinstance(qty, bool) or not isinstance(qty, int) or not 1 <= qty <= MAX_QTY:
            return _error(f"Quantity must be a whole number between 1 and {MAX_QTY}", "BAD_REQUEST", 400)
        quantities[item_id] = quantities.get(item_id, 0) + qty
        if quantities[item_id] > MAX_QTY:
            return _error(f"Quantity per item cannot exceed {MAX_QTY}", "BAD_REQUEST", 400)

    if _rate_limited(_client_ip()):
        return _error("Too many orders from this device. Please try again in a few minutes.",
                      "RATE_LIMITED", 429)

    # --- price every line from the database (never from the client) ---
    try:
        restaurant = _fetch_restaurant(rid)
        if not restaurant:
            return _error("Restaurant not found", "NOT_FOUND", 404)
        item_res = (
            supabase.table("menu_items")
            .select("id, name, selling_price, price, is_active")
            .eq("restaurant_id", rid)
            .eq("is_active", True)
            .in_("id", list(quantities.keys()))
            .execute()
        )
    except Exception as exc:
        return database_error_response(exc, "order item pricing")

    found = {row["id"]: row for row in (item_res.data if item_res and item_res.data else [])}
    if set(found) != set(quantities):
        return _error("Some items in your cart are no longer available. Please refresh the menu.",
                      "ITEMS_UNAVAILABLE", 409)

    lines = []
    total = 0.0
    for item_id, qty in quantities.items():
        row = found[item_id]
        name, _desc = _split_name(row.get("name"))
        unit_price = float(row.get("selling_price") or row.get("price") or 0)
        if unit_price <= 0:
            return _error("Some items in your cart are no longer available. Please refresh the menu.",
                          "ITEMS_UNAVAILABLE", 409)
        line_total = round(unit_price * qty, 2)
        total += line_total
        lines.append({
            "restaurant_id": rid,
            "menu_item_id": item_id,
            "item_name": name[:255],
            "unit_price": unit_price,
            "quantity": qty,
            "line_total": line_total,
        })
    total = round(total, 2)

    # --- persist order, then its lines (roll back the header if lines fail) ---
    order_id = None
    try:
        order_res = supabase.table("orders").insert({
            "restaurant_id": rid,
            "table_number": table_number,
            "customer_name": customer_name,
            "customer_phone": customer_phone,
            "notes": _pack_payment_and_notes(payment_method, notes, payment_ref),
            "status": "pending",
            "subtotal": total,
            "total": total,
        }).execute()
        if not order_res or not order_res.data:
            raise RuntimeError("order insert returned no rows")
        order_row = order_res.data[0]
        order_id = order_row["id"]

        for line in lines:
            line["order_id"] = order_id
        items_res = supabase.table("order_items").insert(lines).execute()
        if not items_res or not items_res.data:
            raise RuntimeError("order items insert returned no rows")
    except Exception as exc:
        if order_id:
            try:
                supabase.table("orders").delete().eq("id", order_id).eq("restaurant_id", rid).execute()
            except Exception as cleanup_exc:  # pragma: no cover - best-effort cleanup
                from flask import current_app
                current_app.logger.error("Failed to roll back order %s", order_id, exc_info=cleanup_exc)
        return database_error_response(exc, "order placement")

    return jsonify({
        "success": True,
        "order": {
            "id": order_id,
            "code": _order_code(order_id),
            "status": "pending",
            "total": total,
            "currency": restaurant.get("currency") or "USD",
            "restaurant_name": restaurant.get("name"),
            "table_number": table_number,
            "payment_method": payment_method,
            "payment_ref": payment_ref,
            "created_at": order_row.get("created_at"),
            "updated_at": order_row.get("updated_at"),
            "items": [
                {"name": l["item_name"], "quantity": l["quantity"],
                 "unit_price": l["unit_price"], "line_total": l["line_total"]}
                for l in lines
            ],
        },
    }), 201


@public_bp.route("/orders/<order_id>", methods=["GET"])
def track_order(order_id):
    oid = _valid_uuid(order_id)
    if not oid:
        return _error("Order not found", "NOT_FOUND", 404)

    try:
        order_res = (
            supabase.table("orders")
            .select("id, restaurant_id, status, total, table_number, notes, created_at, updated_at")
            .eq("id", oid)
            .limit(1)
            .execute()
        )
        rows = order_res.data if order_res and isinstance(order_res.data, list) else []
        if not rows:
            return _error("Order not found", "NOT_FOUND", 404)
        order = rows[0]
        restaurant = _fetch_restaurant(order["restaurant_id"])
        items_res = (
            supabase.table("order_items")
            .select("item_name, quantity, unit_price, line_total")
            .eq("order_id", oid)
            .execute()
        )
    except Exception as exc:
        return database_error_response(exc, "order tracking")

    payment_method, payment_ref, _clean_notes = _unpack_payment_and_notes(order.get("notes"))

    return jsonify({
        "success": True,
        "order": {
            "id": order["id"],
            "code": _order_code(order["id"]),
            "status": order["status"],
            "total": float(order.get("total") or 0),
            "currency": (restaurant or {}).get("currency") or "USD",
            "restaurant_name": (restaurant or {}).get("name"),
            "table_number": order.get("table_number"),
            "payment_method": payment_method,
            "payment_ref": payment_ref,
            "created_at": order.get("created_at"),
            "updated_at": order.get("updated_at"),
            "items": [
                {"name": i["item_name"], "quantity": i["quantity"],
                 "unit_price": float(i["unit_price"]), "line_total": float(i["line_total"])}
                for i in (items_res.data if items_res and items_res.data else [])
            ],
        },
    }), 200


@public_bp.route("/restaurants/<restaurant_id>/led", methods=["GET"])
def public_led_board(restaurant_id):
    """
    Public LED / Kitchen Display board feed for a restaurant.
    Returns active orders (pending, accepted, preparing, ready) with table number,
    order code, status, timestamps, notes, and item names/quantities.
    Never exposes customer phone numbers or financial totals.
    """
    rid = _valid_uuid(restaurant_id)
    if not rid:
        return _error("Restaurant not found", "NOT_FOUND", 404)

    active_statuses = ["pending", "accepted", "preparing", "ready"]
    try:
        restaurant = _fetch_restaurant(rid)
        if not restaurant:
            return _error("Restaurant not found", "NOT_FOUND", 404)

        order_res = (
            supabase.table("orders")
            .select("id, table_number, status, notes, created_at, updated_at")
            .eq("restaurant_id", rid)
            .in_("status", active_statuses)
            .order("created_at", desc=False)
            .limit(100)
            .execute()
        )
        raw_orders = order_res.data if order_res and order_res.data else []

        items_by_order = defaultdict(list)
        if raw_orders:
            items_res = (
                supabase.table("order_items")
                .select("order_id, item_name, quantity")
                .eq("restaurant_id", rid)
                .in_("order_id", [o["id"] for o in raw_orders])
                .execute()
            )
            for item in (items_res.data if items_res and items_res.data else []):
                items_by_order[item["order_id"]].append({
                    "name": item.get("item_name"),
                    "quantity": item.get("quantity"),
                })
    except Exception as exc:
        return database_error_response(exc, "led board query")

    board_orders = []
    for o in raw_orders:
        payment_method, payment_ref, clean_notes = _unpack_payment_and_notes(o.get("notes"))
        board_orders.append({
            "id": o["id"],
            "code": _order_code(o["id"]),
            "table_number": o.get("table_number"),
            "status": o.get("status"),
            "payment_method": payment_method,
            "payment_ref": payment_ref,
            "notes": clean_notes,
            "created_at": o.get("created_at"),
            "updated_at": o.get("updated_at"),
            "items": items_by_order.get(o["id"], []),
        })

    return jsonify({
        "success": True,
        "restaurant": {
            "id": restaurant["id"],
            "name": restaurant.get("name"),
        },
        "count": len(board_orders),
        "orders": board_orders,
    }), 200


# ---------------------------------------------------------------------------
# Owner / staff: list + update orders (tenant scoped)
# ---------------------------------------------------------------------------
@orders_bp.route("", methods=["GET"])
@orders_bp.route("/", methods=["GET"])
@require_auth
def list_orders():
    restaurant_id = current_restaurant_id()

    status = request.args.get("status")
    if status and status not in ORDER_STATUSES:
        return _error("Invalid status filter", "BAD_REQUEST", 400)
    try:
        limit = int(request.args.get("limit", 50))
    except ValueError:
        return _error("limit must be a whole number", "BAD_REQUEST", 400)
    limit = max(1, min(limit, MAX_LIST_LIMIT))

    try:
        query = supabase.table("orders").select("*").eq("restaurant_id", restaurant_id)
        if status:
            query = query.eq("status", status)
        order_res = query.order("created_at", desc=True).limit(limit).execute()
        orders = order_res.data if order_res and order_res.data else []

        items_by_order = defaultdict(list)
        if orders:
            items_res = (
                supabase.table("order_items")
                .select("*")
                .eq("restaurant_id", restaurant_id)
                .in_("order_id", [o["id"] for o in orders])
                .execute()
            )
            for item in (items_res.data if items_res and items_res.data else []):
                items_by_order[item["order_id"]].append(item)
    except Exception as exc:
        return database_error_response(exc, "orders list")

    for order in orders:
        payment_method, payment_ref, clean_notes = _unpack_payment_and_notes(order.get("notes"))
        order["code"] = _order_code(order["id"])
        order["payment_method"] = payment_method
        order["payment_ref"] = payment_ref
        order["notes"] = clean_notes
        order["items"] = items_by_order.get(order["id"], [])

    return jsonify({
        "success": True,
        "restaurant_id": restaurant_id,
        "count": len(orders),
        "data": orders,
    }), 200


@orders_bp.route("/<order_id>/status", methods=["PUT"])
@require_auth
def update_order_status(order_id):
    restaurant_id = current_restaurant_id()
    oid = _valid_uuid(order_id)
    if not oid:
        return _error("Order not found", "NOT_FOUND", 404)

    payload = request.get_json(silent=True)
    status = payload.get("status") if isinstance(payload, dict) else None
    if status not in ORDER_STATUSES:
        return _error(f"status must be one of: {', '.join(ORDER_STATUSES)}", "BAD_REQUEST", 400)

    try:
        res = (
            supabase.table("orders")
            .update({"status": status})
            .eq("id", oid)
            .eq("restaurant_id", restaurant_id)
            .execute()
        )
    except Exception as exc:
        return database_error_response(exc, "order status update")

    if not res or not res.data:
        # Same answer for "does not exist" and "belongs to another restaurant".
        return _error("Order not found", "NOT_FOUND", 404)

    order = res.data[0]
    order["code"] = _order_code(order["id"])
    return jsonify({"success": True, "data": order}), 200


@orders_bp.route("/payment-settings", methods=["GET"])
@require_auth
def get_payment_settings():
    restaurant_id = current_restaurant_id()
    try:
        restaurant = _fetch_restaurant(restaurant_id)
    except Exception as exc:
        return database_error_response(exc, "payment settings lookup")
    if not restaurant:
        return _error("Restaurant not found", "NOT_FOUND", 404)
    return jsonify({
        "success": True,
        "data": _clean_payment_details(restaurant.get("payment_details")),
    }), 200


@orders_bp.route("/payment-settings", methods=["PUT"])
@require_auth
def update_payment_settings():
    restaurant_id = current_restaurant_id()
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return _error("JSON body is required", "BAD_REQUEST", 400)

    details = _clean_payment_details(payload)
    try:
        res = (
            supabase.table("restaurants")
            .update({"payment_details": details})
            .eq("id", restaurant_id)
            .execute()
        )
    except Exception as exc:
        if "payment_details" in str(exc) or "42703" in str(exc):
            return _error(
                "Run database migration 005_payment_details.sql in Supabase SQL Editor first.",
                "MIGRATION_REQUIRED",
                503,
            )
        return database_error_response(exc, "payment settings update")

    if not res or not res.data:
        return _error("Restaurant not found", "NOT_FOUND", 404)

    return jsonify({
        "success": True,
        "data": _clean_payment_details(res.data[0].get("payment_details")),
    }), 200

