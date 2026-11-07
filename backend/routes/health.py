from flask import Blueprint, jsonify
from backend.config import Config

health_bp = Blueprint("health", __name__)

@health_bp.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint to verify backend operational status."""
    return jsonify({
        "status": "healthy",
        "service": "Restaurant Money Engine API",
        "version": "1.0.0",
        "environment": Config.ENV
    }), 200

