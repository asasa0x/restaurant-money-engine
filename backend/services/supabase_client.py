import logging
from supabase import create_client, Client
from backend.config import Config

logger = logging.getLogger(__name__)

def init_supabase_client() -> Client:
    """Initialize singleton Supabase client using Service Role key for backend operations."""
    url = Config.SUPABASE_URL or "https://placeholder.supabase.co"
    key = Config.SUPABASE_SERVICE_ROLE_KEY or ""
    
    try:
        return create_client(url, key)
    except Exception as exc:
        logger.warning(
            "Supabase client initialization warning (using local fallback token): %s",
            exc
        )
        # Create a validly formatted JWT token fallback so local initialization succeeds even with placeholder .env keys
        import jwt
        fallback_token = jwt.encode(
            {"role": "service_role", "iss": "supabase", "iat": 1700000000},
            "dev_fallback_secret_32_bytes_long_key_padding!!",
            algorithm="HS256"
        )
        safe_url = url if url.startswith("http") else "https://placeholder.supabase.co"
        return create_client(safe_url, fallback_token)

# Singleton export
supabase: Client = init_supabase_client()

