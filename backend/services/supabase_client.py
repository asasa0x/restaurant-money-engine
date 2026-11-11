import logging
import jwt
from supabase import create_client, Client
from backend.config import Config

logger = logging.getLogger(__name__)


def _build_bootstrap_jwt() -> str:
    return jwt.encode(
        {"role": "service_role", "iss": "supabase", "iat": 1700000000},
        "dev_fallback_secret_32_bytes_long_key_padding!!",
        algorithm="HS256"
    )


def _apply_api_key(client: Client, key: str) -> Client:
    """Apply an opaque Supabase API key (sb_secret_* / sb_publishable_*) across all sub-clients."""
    client.supabase_key = key
    auth_headers = {
        "apiKey": key,
        "Authorization": f"Bearer {key}",
    }
    client.options.headers.update(auth_headers)
    if hasattr(client, "auth") and hasattr(client.auth, "_headers"):
        client.auth._headers.update(auth_headers)
        if hasattr(client.auth, "admin") and hasattr(client.auth.admin, "_headers"):
            client.auth.admin._headers.update(auth_headers)
    if hasattr(client, "realtime"):
        client.realtime.access_token = key
    client._postgrest = None
    client._storage = None
    client._functions = None
    return client


def init_supabase_client() -> Client:
    """Initialize singleton Supabase client using Service Role key for backend operations."""
    url = Config.SUPABASE_URL or "https://placeholder.supabase.co"
    safe_url = url if url.startswith("http") else "https://placeholder.supabase.co"
    key = Config.SUPABASE_SERVICE_ROLE_KEY or Config.SUPABASE_ANON_KEY or ""

    # Support modern Supabase API keys (sb_secret_* / sb_publishable_*) in supabase==2.13.0
    if key.startswith(("sb_secret_", "sb_publishable_")):
        client = create_client(safe_url, _build_bootstrap_jwt())
        return _apply_api_key(client, key)

    try:
        return create_client(url, key)
    except Exception as exc:
        logger.warning(
            "Supabase client initialization warning (using local fallback token): %s",
            exc
        )
        return create_client(safe_url, _build_bootstrap_jwt())


# Singleton export
supabase: Client = init_supabase_client()


def restore_service_role_auth(client: Client = None) -> None:
    """
    Restore the configured service-role API key on the singleton client after
    a user-facing auth call (such as sign_in_with_password) mutates session headers.
    """
    target = client or supabase
    key = Config.SUPABASE_SERVICE_ROLE_KEY or Config.SUPABASE_ANON_KEY or ""
    if key:
        _apply_api_key(target, key)

