"""Consistent database/auth failure handling. Never leaks raw exception text to clients."""
import httpx
from flask import current_app, jsonify


def is_connectivity_error(exc):
    """True when the failure means the upstream service is unreachable (maps to 503)."""
    return isinstance(exc, (httpx.TransportError, ConnectionError, TimeoutError))


def database_error_response(exc, action):
    """
    Log the real error server-side and return a generic 5xx JSON response.
    503 when the database is unreachable, 500 for any other database failure.
    """
    current_app.logger.error("Database error during %s", action, exc_info=exc)
    if is_connectivity_error(exc):
        return jsonify({
            "success": False,
            "error": "Database is temporarily unavailable. Please try again later.",
            "code": "DATABASE_UNAVAILABLE"
        }), 503
    return jsonify({
        "success": False,
        "error": "Database operation failed.",
        "code": "DATABASE_ERROR"
    }), 500

