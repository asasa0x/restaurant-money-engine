from functools import wraps
from flask import request, jsonify, g, current_app
from backend.services.supabase_client import supabase
from backend.middleware.errors import database_error_response, is_connectivity_error


def _unauthorized(message):
    return jsonify({
        "success": False,
        "error": message,
        "code": "UNAUTHORIZED"
    }), 401


def _forbidden(message, code):
    return jsonify({
        "success": False,
        "error": message,
        "code": code
    }), 403


def _first_row(data):
    """Normalize a PostgREST result into a single dict row (or None)."""
    if isinstance(data, list):
        return data[0] if data and isinstance(data[0], dict) else None
    if isinstance(data, dict):
        return data
    return None


def require_auth(f):
    """
    Decorator for multi-tenant authenticated routes. Fails closed.
    - Extracts Bearer token from Authorization header.
    - Validates token using supabase.auth.get_user(token).
    - Queries `profiles` table for the caller's restaurant_id and role.
    - Sets g.user, g.restaurant_id, g.role.
    - 401: missing/invalid token.
    - 403: valid user but no profile, or profile without a restaurant_id.
    - 5xx: authentication service or profile lookup is unavailable/failing.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get("Authorization")
        if not auth_header:
            return _unauthorized("Missing Authorization header")

        parts = auth_header.split(" ")
        if len(parts) != 2 or parts[0].lower() != "bearer":
            return _unauthorized("Invalid Authorization header format. Expected 'Bearer <token>'")

        token = parts[1].strip()
        if not token:
            return _unauthorized("Bearer token is empty")

        # Validate token with Supabase Auth
        try:
            auth_response = supabase.auth.get_user(token)
        except Exception as exc:
            if is_connectivity_error(exc):
                current_app.logger.error("Auth service unreachable", exc_info=exc)
                return jsonify({
                    "success": False,
                    "error": "Authentication service is temporarily unavailable.",
                    "code": "AUTH_SERVICE_UNAVAILABLE"
                }), 503
            # Do not leak provider error text to the client
            current_app.logger.info("Token verification failed: %s", type(exc).__name__)
            return _unauthorized("Invalid or expired token")

        user = getattr(auth_response, "user", None) if auth_response else None
        user_id = getattr(user, "id", None) if user else None
        if not user or not user_id:
            return _unauthorized("Invalid or expired token")

        # Resolve tenant: profile lookup must succeed and contain a restaurant_id
        try:
            profile_res = (
                supabase.table("profiles")
                .select("restaurant_id, role")
                .eq("id", user_id)
                .limit(1)
                .execute()
            )
        except Exception as exc:
            return database_error_response(exc, "profile lookup")

        row = _first_row(profile_res.data if profile_res else None)
        if row is None:
            return _forbidden("No profile exists for this account.", "PROFILE_NOT_FOUND")

        raw_restaurant_id = row.get("restaurant_id")
        if raw_restaurant_id is None or not str(raw_restaurant_id).strip():
            return _forbidden("This account is not assigned to a restaurant.", "RESTAURANT_NOT_ASSIGNED")

        g.user = user
        g.restaurant_id = str(raw_restaurant_id)
        g.role = str(row.get("role") or "member")

        return f(*args, **kwargs)

    return decorated_function
