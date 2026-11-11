"""Tenant context helpers. Routes must never run a tenant query without a restaurant_id."""
from flask import g


class TenantContextError(Exception):
    """Raised when a route runs without an authenticated restaurant context (maps to HTTP 403)."""


def current_restaurant_id():
    """
    Return the authenticated caller's restaurant_id or raise TenantContextError.
    Defense in depth: require_auth already blocks callers without a restaurant, and
    routes use this helper so a tenant filter can never be silently skipped.
    """
    restaurant_id = getattr(g, "restaurant_id", None)
    if restaurant_id is None or not str(restaurant_id).strip():
        raise TenantContextError("No restaurant context for this request")
    return str(restaurant_id)

