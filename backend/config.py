import os
import secrets
from pathlib import Path
from dotenv import load_dotenv

# Absolute path resolution based on pathlib
BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent
DOTENV_PATH = (ROOT_DIR / ".env").resolve()

# Load root .env using absolute pathlib path
if DOTENV_PATH.is_file():
    load_dotenv(dotenv_path=DOTENV_PATH, override=True)

MIN_PRODUCTION_SECRET_LENGTH = 32
INSECURE_SECRET_PREFIXES = ("dev-secret", "your-", "change-me", "changeme", "replace")


def validate_production_config(config_class):
    """
    Fail startup (RuntimeError) when running in production without a strong SECRET_KEY.
    Missing, placeholder, or short (<32 chars) keys are rejected.
    """
    if str(getattr(config_class, "ENV", "")).lower() != "production":
        return
    secret = getattr(config_class, "SECRET_KEY", None)
    if (
        not secret
        or len(str(secret)) < MIN_PRODUCTION_SECRET_LENGTH
        or str(secret).lower().startswith(INSECURE_SECRET_PREFIXES)
    ):
        raise RuntimeError(
            "SECRET_KEY is missing or insecure. In production set SECRET_KEY to a random value "
            f"of at least {MIN_PRODUCTION_SECRET_LENGTH} characters."
        )

class Config:
    """Application configuration for Restaurant Money Engine backend."""

    BASE_DIR = BASE_DIR
    ROOT_DIR = ROOT_DIR
    DOTENV_PATH = DOTENV_PATH

    # Flask Core Settings
    PORT = int(os.getenv("PORT", 5000))
    HOST = os.getenv("HOST", "0.0.0.0")
    ENV = os.getenv("FLASK_ENV", "development").lower()
    
    # Strictly disable debug mode in production
    if ENV == "production":
        DEBUG = False
    else:
        DEBUG = os.getenv("FLASK_DEBUG", "True").lower() in ("true", "1", "t")

    # No hard-coded default. Production must provide a strong SECRET_KEY (validated at startup
    # by validate_production_config). Outside production an ephemeral random key is generated.
    SECRET_KEY = os.getenv("SECRET_KEY", "").strip() or (
        None if ENV == "production" else secrets.token_hex(32)
    )

    # CORS Origins (Restricted in production, flexible in development)
    raw_cors = os.getenv("CORS_ORIGINS", "")
    if raw_cors and raw_cors.strip() != "*":
        CORS_ORIGINS = [origin.strip() for origin in raw_cors.split(",") if origin.strip()]
    elif ENV == "production":
        CORS_ORIGINS = [
            r"https://.*\.vercel\.app",
            r"https://restaurant-money-engine.*\.vercel\.app"
        ]
    else:
        CORS_ORIGINS = [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:5000",
            "http://127.0.0.1:5000",
            "http://localhost:5500",
            "http://127.0.0.1:5500"
        ]

    # Supabase & PostgreSQL (Strictly server-side; never exposed to frontend)
    SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip()
    SUPABASE_KEY = os.getenv("SUPABASE_KEY", "").strip()
    SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "").strip() or SUPABASE_KEY
    SUPABASE_SERVICE_ROLE_KEY = (
        os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip() or SUPABASE_KEY
    )
    DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

    @classmethod
    def is_configured(cls) -> bool:
        """Helper to check if essential Supabase credentials are provided."""
        has_url = bool(
            cls.SUPABASE_URL
            and "your-project-id" not in cls.SUPABASE_URL
            and "placeholder" not in cls.SUPABASE_URL
        )
        has_key = bool(
            (cls.SUPABASE_SERVICE_ROLE_KEY and not cls.SUPABASE_SERVICE_ROLE_KEY.startswith("your-"))
            or (cls.SUPABASE_ANON_KEY and not cls.SUPABASE_ANON_KEY.startswith("your-"))
        )
        return has_url and has_key
