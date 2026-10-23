"""Health endpoint: whether the gateway runs, reaches the platform and how many readings wait."""
from flask import Blueprint, current_app, jsonify

health_api = Blueprint("health_api", __name__)


@health_api.get("/api/v1/health")
def health():
    services = current_app.extensions["ososense"]
    return jsonify(
        status="UP",
        platformReachable=services.connectivity.is_online(),
        readings=services.readings.count_by_status(),
    )
