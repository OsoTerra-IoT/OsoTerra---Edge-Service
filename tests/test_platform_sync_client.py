from datetime import datetime, timezone

import requests

from monitoring.domain.entities import SoilReading
from monitoring.infrastructure.platform_sync_client import PlatformSyncClient, SubmissionOutcome


class FakeResponse:
    def __init__(self, status_code, body=None):
        self.status_code = status_code
        self._body = body
        self.text = "" if body is None else str(body)

    @property
    def ok(self):
        return 200 <= self.status_code < 300

    def json(self):
        if self._body is None:
            raise ValueError("no body")
        return self._body


class FakeSession:
    def __init__(self, response=None, error=None):
        self.response, self.error, self.calls = response, error, []

    def post(self, url, json, timeout, headers):
        self.calls.append({"url": url, "json": json, "headers": headers})
        if self.error:
            raise self.error
        return self.response


def sample_reading():
    return SoilReading(id=1, device_code="OS-014", platform_device_id=7, raw_conductivity_dsm=2.2,
                       compensated_conductivity_dsm=2.0, compensation_factor=0.9091, moisture_percentage=35.0,
                       temperature_celsius=30.0, captured_at=datetime(2026, 10, 19, 15, 30, 0))


def make_client(session, tz="utc"):
    return PlatformSyncClient("http://platform:8080/", "edge-key", platform_timezone=tz, session=session)


def test_sends_the_contract_payload_with_the_edge_key():
    session = FakeSession(FakeResponse(201, {"id": 42, "acceptedCount": 1, "discardedCount": 0}))

    result = make_client(session).submit_batch(7, [sample_reading()])

    call = session.calls[0]
    assert call["url"] == "http://platform:8080/api/v1/soil-readings/batches"
    assert call["headers"] == {"X-Edge-Api-Key": "edge-key"}
    assert call["json"] == {"deviceId": 7, "readings": [{
        "rawConductivityDsM": 2.2, "compensatedConductivityDsM": 2.0, "compensationFactor": 0.9091,
        "moisturePercentage": 35.0, "temperatureCelsius": 30.0, "capturedAt": "2026-10-19T15:30:00.000"}]}
    assert result.outcome == SubmissionOutcome.ACCEPTED
    assert result.platform_batch_id == 42


def test_local_timezone_converts_the_utc_capture_time():
    session = FakeSession(FakeResponse(201, {"id": 1}))
    make_client(session, tz="local").submit_batch(7, [sample_reading()])

    sent = session.calls[0]["json"]["readings"][0]["capturedAt"]
    expected = datetime(2026, 10, 19, 15, 30).replace(tzinfo=timezone.utc).astimezone()
    assert sent == expected.replace(tzinfo=None).isoformat(timespec="milliseconds")


def test_bad_request_means_rejected():
    result = make_client(FakeSession(FakeResponse(400, {"message": "invalid"}))).submit_batch(7, [sample_reading()])
    assert result.outcome == SubmissionOutcome.REJECTED
    assert result.detail == "HTTP 400: invalid"


def test_auth_or_missing_device_means_retry_later():
    for status in (401, 404):
        result = make_client(FakeSession(FakeResponse(status, {"message": "x"}))).submit_batch(7, [sample_reading()])
        assert result.outcome == SubmissionOutcome.RETRY_LATER
        assert not result.server_error


def test_server_error_is_flagged():
    result = make_client(FakeSession(FakeResponse(500))).submit_batch(7, [sample_reading()])
    assert result.outcome == SubmissionOutcome.RETRY_LATER
    assert result.server_error


def test_connection_error_means_unreachable():
    session = FakeSession(error=requests.ConnectionError("refused"))
    result = make_client(session).submit_batch(7, [sample_reading()])
    assert result.outcome == SubmissionOutcome.UNREACHABLE
