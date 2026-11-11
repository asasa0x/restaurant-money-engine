from flask import Flask, jsonify, send_from_directory, request
from flask_cors import CORS
from backend.config import Config, validate_production_config
from backend.middleware.tenant import TenantContextError
from backend.routes import register_routes

def create_app(config_class=Config):
    """Application factory for Restaurant Money Engine backend (Production & Gunicorn ready)."""
    # Refuse to start in production with a missing/insecure SECRET_KEY
    validate_production_config(config_class)

    frontend_dir = Config.ROOT_DIR / "frontend"

    app = Flask(
        __name__,
        static_folder=str(frontend_dir),
        static_url_path=""
    )
    app.config.from_object(config_class)

    # Fail closed if any route ever runs without a restaurant context
    @app.errorhandler(TenantContextError)
    def handle_tenant_context_error(_exc):
        return jsonify({
            "success": False,
            "error": "No restaurant context for this request.",
            "code": "FORBIDDEN_NO_RESTAURANT"
        }), 403

    # Configure CORS for frontend-backend communication (e.g. Vercel <-> Render)
    CORS(app, resources={r"/*": {"origins": Config.CORS_ORIGINS}})

    # Apply strict HTTP security headers
    @app.after_request
    def apply_security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response

    # Register API blueprints (/health, /api/v1/daily-financials, /api/v1/menu-matrix, /api/v1/menu, /api/v1/simulation)
    register_routes(app)

    # Root API metadata route
    @app.route("/", methods=["GET"])
    def root():
        # Check accept header: if browser requested HTML, serve dashboard, else JSON API
        if "text/html" in request.headers.get("Accept", ""):
            return send_from_directory(str(frontend_dir), "index.html")
        return jsonify({
            "name": "Restaurant Money Engine API",
            "version": "1.0.0",
            "status": "online",
            "environment": Config.ENV,
            "dashboard_ui": "/dashboard",
            "endpoints": [
                "/health",
                "/api/v1/daily-financials",
                "/api/v1/menu-matrix",
                "/api/v1/menu",
                "/api/v1/simulation/run"
            ]
        }), 200

    @app.route("/dashboard", methods=["GET"])
    @app.route("/app", methods=["GET"])
    def dashboard_ui():
        return send_from_directory(str(frontend_dir), "index.html")

    return app

app = create_app()

if __name__ == "__main__":
    print(f"🚀 Starting Restaurant Money Engine API on http://{Config.HOST}:{Config.PORT} (Debug={Config.DEBUG})")
    app.run(host=Config.HOST, port=Config.PORT, debug=Config.DEBUG)
