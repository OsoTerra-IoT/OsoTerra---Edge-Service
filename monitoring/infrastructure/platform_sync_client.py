"""HTTP client that hands reading batches to the platform's Telemetry Ingestion endpoint."""
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

import requests

from monitoring.domain.entities import SoilReading

logger = logging.getLogger(__name__)

BATCHES_PATH = "/api/v1/soil-readings/batches"


class SubmissionOutcome(str, Enum):
    ACCEPTED = "ACCEPTED"          # 2xx: the platform stored the batch
    REJECTED = "REJECTED"          # 400: the payload itself is invalid; resending will not help
    RETRY_LATER = "RETRY_LATER"    # no connection, bad key, device not linked yet, server error
    UNREACHABLE = "UNREACHABLE"    # connection failed: stop trying until the next cycle


@dataclass(frozen=True)
class SubmissionResult:
    outcome: SubmissionOutcome
    detail: str = ""
    platform_batch_id: int | None = None
    accepted_count: int | None = None
    discarded_count: int | None = None
    server_error: bool = False


class PlatformSyncClient:
    def __init__(self, base_url: str, edge_api_key: str, timeout_seconds: float = 5.0,
                 platform_timezone: str = "local", session: requests.Session | None = None):
        self._url = base_url.rstrip("/") + BATCHES_PATH
        self._edge_api_key = edge_api_key
        self._timeout = timeout_seconds
        self._platform_timezone = platform_timezone
        self._session = session or requests.Session()

    def submit_batch(self, platform_device_id: int, readings: list[SoilReading]) -> SubmissionResult:
        body = {"deviceId": platform_device_id, "readings": [self._to_payload(r) for r in readings]}
        try:
            response = self._session.post(
                self._url, json=body, timeout=self._timeout, headers={"X-Edge-Api-Key": self._edge_api_key})
        except requests.RequestException as error:
            logger.warning("Platform unreachable: %s", error)
            return SubmissionResult(SubmissionOutcome.UNREACHABLE, f"Platform unreachable: {type(error).__name__}")

        if response.ok:
            data = _json_or_empty(response)
            return SubmissionResult(SubmissionOutcome.ACCEPTED, platform_batch_id=data.get("id"),
                                    accepted_count=data.get("acceptedCount"),
                                    discarded_count=data.get("discardedCount"))
        detail = f"HTTP {response.status_code}: {_json_or_empty(response).get('message', response.text[:200])}"
        logger.warning("Platform answered %s", detail)
        if response.status_code == 400:
            return SubmissionResult(SubmissionOutcome.REJECTED, detail)
        return SubmissionResult(SubmissionOutcome.RETRY_LATER, detail, server_error=response.status_code >= 500)

    def _to_payload(self, reading: SoilReading) -> dict:
        return {
            "rawConductivityDsM": reading.raw_conductivity_dsm,
            "compensatedConductivityDsM": reading.compensated_conductivity_dsm,
            "compensationFactor": reading.compensation_factor,
            "moisturePercentage": reading.moisture_percentage,
            "temperatureCelsius": reading.temperature_celsius,
            "capturedAt": self._platform_time(reading.captured_at),
        }

    def _platform_time(self, captured_at_utc: datetime) -> str:
        """The platform expects a LocalDateTime (no offset) in its own clock's time zone."""
        moment = captured_at_utc.replace(tzinfo=timezone.utc)
        if self._platform_timezone != "utc":
            moment = moment.astimezone()
        return moment.replace(tzinfo=None).isoformat(timespec="milliseconds")


def _json_or_empty(response: requests.Response) -> dict:
    try:
        data = response.json()
        return data if isinstance(data, dict) else {}
    except ValueError:
        return {}
