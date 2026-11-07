from .health import health_bp
from .engine import engine_bp
from .menu import menu_bp
from .simulation import simulation_bp

def register_routes(app):
    """Register all API route blueprints."""
    # Mount health route (/health)
    app.register_blueprint(health_bp)
    # Mount core money engine API routes (/api/v1/daily-financials, /api/v1/menu-matrix)
    app.register_blueprint(engine_bp)
    # Mount menu & recipe costing routes (/api/v1/menu)
    app.register_blueprint(menu_bp)
    # Mount what-if profit simulation route (/api/v1/simulation)
    app.register_blueprint(simulation_bp)
