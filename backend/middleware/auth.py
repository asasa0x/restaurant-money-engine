from functools import wraps
from flask import request, jsonify, g
from backend.services.supabase_client import supabase

def require_auth(f):
    """
    Decorator for multi-tenant authenticated routes.
    - Extracts Bearer token from Authorization header.
    - Validates token using supabase.auth.get_user(token).
    - Queries `profiles` table for caller's restaurant_id and role.
    - Sets g.user, g.restaurant_id, g.role.
    - Returns 401 on missing or invalid token.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get("Authorization")
        if not auth_header:
            return jsonify({
                "success": False,
                "error": "Missing Authorization header",
                "code": "UNAUTHORIZED"
            }), 401

        parts = auth_header.split(" ")
        if len(parts) != 2 or parts[0].lower() != "bearer":
            return jsonify({
                "success": False,
                "error": "Invalid Authorization header format. Expected 'Bearer <token>'",
                "code": "UNAUTHORIZED"
            }), 401

        token = parts[1].strip()
        if not token:
            return jsonify({
                "success": False,
                "error": "Bearer token is empty",
                "code": "UNAUTHORIZED"
            }), 401

        # Validate token with Supabase Auth
        try:
            auth_response = supabase.auth.get_user(token)
            if not auth_response or not getattr(auth_response, "user", None):
                return jsonify({
                    "success": False,
                    "error": "Invalid or expired token",
                    "code": "UNAUTHORIZED"
                }), 401
            
            user = auth_response.user
        except Exception as exc:
            return jsonify({
                "success": False,
                "error": "Authentication verification failed",
                "details": str(exc),
                "code": "UNAUTHORIZED"
            }), 401

        # Query user profile for restaurant tenancy & role
        restaurant_id = None
        role = "member"

        try:
            user_id = getattr(user, "id", None)
            if user_id:
                profile_res = (
                    supabase.table("profiles")
                    .select("restaurant_id, role")
                    .eq("id", user_id)
                    .single()
                    .execute()
                )
                if profile_res and profile_res.data and isinstance(profile_res.data, dict):
                    raw_rest_id = profile_res.data.get("restaurant_id")
                    restaurant_id = str(raw_rest_id) if raw_rest_id is not None else None
                    role = str(profile_res.data.get("role", "member"))
        except Exception:
            # If profiles table has no record yet or is unavailable, default gracefully
            pass

        # Attach tenant context to Flask global context
        g.user = user
        g.restaurant_id = restaurant_id
        g.role = role

        return f(*args, **kwargs)

    return decorated_function

