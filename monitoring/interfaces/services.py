"""REST endpoints of the Soil Monitoring context (TelemetryConsumer in chapter 4)."""
from datetime import datetime, timezone

from flask import Blueprint, current_app, jsonify, request

from monitoring.application.services import CaptureReadingCommand
from monitoring.domain.entities import SoilReading, SyncStatus

monitoring_api = Blueprint("monitoring_api", __name__)


def _services():
    return current_app.extensions["ososense"]


class InvalidPayload(ValueError):
    pass


def _number(body: dict, field: str, required: bool = True) -> float | None:
    value = body.get(field)
    if value is None:
        if required:
            raise InvalidPayload(f"'{field}' is required")
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InvalidPayload(f"'{field}' must be a number")
    return float(value)


def _timestamp(value) -> datetime | None:
    """Accepts ISO-8601; a value without offset is taken as UTC. Returns naive UTC."""
    if value is None:
        return None
    try:
        moment = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as error:
        raise InvalidPayload("'capturedAt' must be an ISO-8601 date-time") from error
    if moment.tzinfo is not None:
        moment = moment.astimezone(timezone.utc).replace(tzinfo=None)
    return moment


def to_resource(reading: SoilReading) -> dict:
    return {
        "id": reading.id,
        "deviceId": reading.device_code,
        "platformDeviceId": reading.platform_device_id,
        "rawConductivityDsM": reading.raw_conductivity_dsm,
        "compensatedConductivityDsM": reading.compensated_conductivity_dsm,
        "compensationFactor": reading.compensation_factor,
        "moisturePercentage": reading.moisture_percentage,
        "temperatureCelsius": reading.temperature_celsius,
        "capturedAt": reading.captured_at.isoformat(timespec="milliseconds") + "Z",
        "status": reading.status.value,
        "statusReason": reading.status_reason,
        "platformBatchId": reading.platform_batch_id,
    }


@monitoring_api.post("/api/v1/soil-readings")
def capture_reading():
    """Receives one reading from the Embedded Application."""
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify(message="A JSON object is required"), 400

    device = _services().auth.authenticate(body.get("deviceId"), request.headers.get("X-API-Key"))
    if device is None:
        return jsonify(message="Unknown device or invalid X-API-Key"), 401

    try:
        command = CaptureReadingCommand(
            device=device,
            conductivity_dsm=_number(body, "conductivityDsM"),
            moisture_percentage=_number(body, "moisturePercent"),
            temperature_celsius=_number(body, "temperatureCelsius", required=False),
            captured_at=_timestamp(body.get("capturedAt")),
        )
    except InvalidPayload as error:
        return jsonify(message=str(error)), 400

    reading, created = _services().capture.handle(command)
    if reading.status == SyncStatus.DISCARDED:
        return jsonify(to_resource(reading)), 422
    return jsonify(to_resource(reading)), 201 if created else 200


@monitoring_api.get("/api/v1/soil-readings")
def list_readings():
    status = request.args.get("status")
    try:
        status_filter = SyncStatus(status.upper()) if status else None
    except ValueError:
        return jsonify(message=f"Unknown status '{status}'"), 400
    limit = min(request.args.get("limit", default=50, type=int), 500)
    readings = _services().readings.find_latest(status_filter, limit)
    return jsonify([to_resource(reading) for reading in readings])


@monitoring_api.post("/api/v1/soil-readings/synchronizations")
def synchronize_now():
    """Forces a synchronization cycle (the scheduler also runs one every SYNC_INTERVAL_SECONDS)."""
    report = _services().synchronize.handle()
    return jsonify(
        attempted=report.attempted,
        platformReachable=report.platform_reachable,
        synchronized=report.synchronized,
        rejected=report.rejected,
        givenUp=report.given_up,
        stillPending=report.still_pending,
    )
