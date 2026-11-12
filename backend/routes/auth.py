import logging
from flask import Blueprint, request, jsonify, g
from backend.middleware.auth import require_auth
from backend.middleware.errors import database_error_response
from backend.middleware.tenant import current_restaurant_id
from backend.services.supabase_client import supabase, restore_service_role_auth

logger = logging.getLogger(__name__)

auth_bp = Blueprint("auth", __name__, url_prefix="/api/v1/auth")


def _bad_request(message):
    return jsonify({"success": False, "error": message, "code": "BAD_REQUEST"}), 400


@auth_bp.route("/signup", methods=["POST"])
def signup():
    """
    POST /api/v1/auth/signup
    Creates a new Supabase Auth user, provisions a tenant restaurant and owner profile,
    and returns an authenticated JWT session.
    """
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return _bad_request("Request body must be a JSON object")

    email = str(payload.get("email") or "").strip().lower()
    password = str(payload.get("password") or "")
    restaurant_name = str(payload.get("restaurant_name") or "").strip()
    currency = str(payload.get("currency") or "USD").strip().upper() or "USD"

    if not email or "@" not in email:
        return _bad_request("A valid email address is required")
    if len(password) < 6:
        return _bad_request("Password must be at least 6 characters")
    if not restaurant_name:
        return _bad_request("Restaurant name is required")

    created_user_id = None
    created_restaurant_id = None

    try:
        # 1. Create confirmed Supabase Auth user
        try:
            user_res = supabase.auth.admin.create_user({
                "email": email,
                "password": password,
                "email_confirm": True
            })
        except Exception as exc:
            msg = str(exc)
            if "already" in msg.lower() or "exists" in msg.lower() or "registered" in msg.lower():
                return jsonify({
                    "success": False,
                    "error": "An account with this email already exists",
                    "code": "EMAIL_EXISTS"
                }), 409
            logger.error("Supabase user creation failed: %s", type(exc).__name__)
            return jsonify({
                "success": False,
                "error": "Unable to create user account",
                "code": "SIGNUP_FAILED"
            }), 400

        user_obj = getattr(user_res, "user", None)
        created_user_id = str(getattr(user_obj, "id", "") or "")
        if not created_user_id:
            return jsonify({
                "success": False,
                "error": "Unable to provision user account",
                "code": "SIGNUP_FAILED"
            }), 500

        # 2. Provision tenant restaurant
        rest_res = (
            supabase.table("restaurants")
            .insert({"name": restaurant_name, "currency": currency})
            .execute()
        )
        if not rest_res or not rest_res.data:
            raise RuntimeError("Restaurant provisioning returned no rows")

        restaurant_row = rest_res.data[0]
        created_restaurant_id = restaurant_row["id"]

        # 3. Create owner profile linking user -> restaurant
        prof_res = (
            supabase.table("profiles")
            .insert({
                "id": created_user_id,
                "restaurant_id": created_restaurant_id,
                "role": "owner"
            })
            .execute()
        )
        if not prof_res or not prof_res.data:
            raise RuntimeError("Profile provisioning returned no rows")

        # 4. Issue session JWT via sign_in_with_password
        try:
            sign_in_res = supabase.auth.sign_in_with_password({
                "email": email,
                "password": password
            })
        finally:
            restore_service_role_auth(supabase)

        session = getattr(sign_in_res, "session", None)
        access_token = getattr(session, "access_token", None)
        if not access_token:
            raise RuntimeError("Session token was not returned after signup")

        return jsonify({
            "success": True,
            "access_token": access_token,
            "user": {
                "id": created_user_id,
                "email": email,
                "role": "owner"
            },
            "restaurant": {
                "id": created_restaurant_id,
                "name": restaurant_row.get("name", restaurant_name),
                "currency": restaurant_row.get("currency", currency)
            }
        }), 201

    except Exception as exc:
        restore_service_role_auth(supabase)
        # Rollback partial tenant state on failure
        if created_restaurant_id:
            try:
                supabase.table("restaurants").delete().eq("id", created_restaurant_id).execute()
            except Exception:
                logger.exception("Failed to roll back restaurant %s", created_restaurant_id)
        if created_user_id:
            try:
                supabase.auth.admin.delete_user(created_user_id)
            except Exception:
                logger.exception("Failed to roll back user %s", created_user_id)
        return database_error_response(exc, "account signup provisioning")


@auth_bp.route("/login", methods=["POST"])
def login():
    """
    POST /api/v1/auth/login
    Authenticates user via Supabase Auth and verifies tenant profile & restaurant.
    """
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return _bad_request("Request body must be a JSON object")

    raw_identifier = str(payload.get("email") or payload.get("username") or "").strip().lower()
    email = raw_identifier if "@" in raw_identifier else (f"{raw_identifier}@kitchen.restaurant.local" if raw_identifier else "")
    password = str(payload.get("password") or "")

    if not email or not password:
        return _bad_request("Username/email and password are required")

    try:
        try:
            sign_in_res = supabase.auth.sign_in_with_password({
                "email": email,
                "password": password
            })
        finally:
            restore_service_role_auth(supabase)
    except Exception:
        return jsonify({
            "success": False,
            "error": "Invalid email or password",
            "code": "INVALID_CREDENTIALS"
        }), 401

    session = getattr(sign_in_res, "session", None)
    user_obj = getattr(sign_in_res, "user", None)
    access_token = getattr(session, "access_token", None)
    user_id = str(getattr(user_obj, "id", "") or "")

    if not access_token or not user_id:
        return jsonify({
            "success": False,
            "error": "Invalid email or password",
            "code": "INVALID_CREDENTIALS"
        }), 401

    try:
        prof_res = (
            supabase.table("profiles")
            .select("restaurant_id, role")
            .eq("id", user_id)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        return database_error_response(exc, "login profile lookup")

    rows = prof_res.data if prof_res and isinstance(prof_res.data, list) else []
    if not rows:
        return jsonify({
            "success": False,
            "error": "User profile not found",
            "code": "PROFILE_NOT_FOUND"
        }), 403

    profile = rows[0]
    restaurant_id = profile.get("restaurant_id")
    if not restaurant_id:
        return jsonify({
            "success": False,
            "error": "No restaurant assigned to user profile",
            "code": "RESTAURANT_NOT_ASSIGNED"
        }), 403

    restaurant_data = {"id": restaurant_id, "name": "Restaurant", "currency": "USD"}
    try:
        rest_res = (
            supabase.table("restaurants")
            .select("id, name, currency")
            .eq("id", restaurant_id)
            .limit(1)
            .execute()
        )
        if rest_res and rest_res.data:
            restaurant_data = rest_res.data[0]
    except Exception as exc:
        return database_error_response(exc, "login restaurant lookup")

    return jsonify({
        "success": True,
        "access_token": access_token,
        "user": {
            "id": user_id,
            "email": getattr(user_obj, "email", email) or email,
            "role": profile.get("role") or "member"
        },
        "restaurant": restaurant_data
    }), 200


@auth_bp.route("/me", methods=["GET"])
@require_auth
def get_current_session():
    """
    GET /api/v1/auth/me
    Returns the authenticated user's profile and active restaurant details.
    """
    restaurant_id = current_restaurant_id()
    user_obj = getattr(g, "user", None)
    user_id = str(getattr(user_obj, "id", "") or "")
    user_email = getattr(user_obj, "email", None) or (
        user_obj.get("email") if isinstance(user_obj, dict) else ""
    )

    restaurant_data = {"id": restaurant_id, "name": "Restaurant", "currency": "USD"}
    try:
        rest_res = (
            supabase.table("restaurants")
            .select("id, name, currency")
            .eq("id", restaurant_id)
            .limit(1)
            .execute()
        )
        if rest_res and rest_res.data:
            restaurant_data = rest_res.data[0]
    except Exception as exc:
        return database_error_response(exc, "current restaurant lookup")

    return jsonify({
        "success": True,
        "user": {
            "id": user_id,
            "email": user_email or "",
            "role": getattr(g, "role", "member")
        },
        "restaurant": restaurant_data
    }), 200

