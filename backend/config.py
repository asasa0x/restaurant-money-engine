import os
from pathlib import Path
from dotenv import load_dotenv

# Absolute path resolution based on pathlib
BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent
DOTENV_PATH = (ROOT_DIR / ".env").resolve()

# Load root .env using absolute pathlib path
if DOTENV_PATH.is_file():
    load_dotenv(dotenv_path=DOTENV_PATH, override=True)

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

    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-replace-in-production")

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
    SUPABASE_URL = os.getenv("SUPABASE_URL", "")
    SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")
    SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    DATABASE_URL = os.getenv("DATABASE_URL", "")

    @classmethod
    def is_configured(cls) -> bool:
        """Helper to check if essential Supabase credentials are provided."""
        return bool(cls.SUPABASE_URL and cls.SUPABASE_ANON_KEY and cls.DATABASE_URL)
