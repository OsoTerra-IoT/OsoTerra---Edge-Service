from datetime import datetime, timedelta, timezone

from monitoring.infrastructure.platform_sync_client import SubmissionOutcome, SubmissionResult
from tests.conftest import HEADERS, reading


def iso_minutes_ago(minutes):
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()


def test_unknown_device_or_wrong_key_is_unauthorized(client, platform):
    assert client.post("/api/v1/soil-readings", json=reading(deviceId="OS-999"), headers=HEADERS).status_code == 401
    assert client.post("/api/v1/soil-readings", json=reading(), headers={"X-API-Key": "nope"}).status_code == 401
    assert client.post("/api/v1/soil-readings", json=reading()).status_code == 401
    assert platform.batches == []


def test_malformed_payloads_are_bad_requests(client):
    assert client.post("/api/v1/soil-readings", data="not json", headers=HEADERS).status_code == 400
    missing = reading()
    del missing["conductivityDsM"]
    assert client.post("/api/v1/soil-readings", json=missing, headers=HEADERS).status_code == 400
    assert client.post("/api/v1/soil-readings", json=reading(moisturePercent="40"), headers=HEADERS).status_code == 400
    assert client.post("/api/v1/soil-readings", json=reading(capturedAt="yesterday"), headers=HEADERS).status_code == 400


def test_valid_reading_is_compensated_and_sent_right_away(client, platform):
    response = client.post("/api/v1/soil-readings", json=reading(conductivityDsM=2.2, temperatureCelsius=30.0),
                           headers=HEADERS)

    assert response.status_code == 201
    body = response.get_json()
    assert body["rawConductivityDsM"] == 2.2
    assert body["compensatedConductivityDsM"] == 2.0
    assert body["status"] == "SYNCHRONIZED"
    assert body["platformBatchId"] == 1
    assert platform.batches == [(7, [body["id"]])]


def test_calibration_factor_of_the_device_is_applied(client):
    body = client.post("/api/v1/soil-readings", json=reading(deviceId="OS-015"),
                       headers={"X-API-Key": "other-key"}).get_json()
    assert body["compensatedConductivityDsM"] == 2.2
    assert body["platformDeviceId"] == 8


def test_out_of_range_reading_is_discarded_and_never_sent(client, platform):
    response = client.post("/api/v1/soil-readings", json=reading(conductivityDsM=35.0), headers=HEADERS)

    assert response.status_code == 422
    assert response.get_json()["status"] == "DISCARDED"
    assert "Conductivity" in response.get_json()["statusReason"]
    assert platform.batches == []


def test_reading_without_temperature_is_kept_raw_and_not_sent(client, platform):
    response = client.post("/api/v1/soil-readings", json=reading(temperatureCelsius=None), headers=HEADERS)

    body = response.get_json()
    assert response.status_code == 201
    assert body["status"] == "UNCOMPENSATED"
    assert body["compensatedConductivityDsM"] is None
    assert body["rawConductivityDsM"] == 2.0
    assert platform.batches == []


def test_repeated_capture_returns_the_stored_reading(client, platform):
    captured = iso_minutes_ago(1)
    first = client.post("/api/v1/soil-readings", json=reading(capturedAt=captured), headers=HEADERS)
    second = client.post("/api/v1/soil-readings", json=reading(capturedAt=captured), headers=HEADERS)

    assert first.status_code == 201
    assert second.status_code == 200
    assert second.get_json()["id"] == first.get_json()["id"]
    assert len(platform.batches) == 1


def test_offline_readings_are_buffered_and_sent_in_chronological_order(client, platform, connectivity):
    connectivity.online = False
    ids = []
    for minutes in (10, 30, 20):  # arrive out of order
        body = client.post("/api/v1/soil-readings", json=reading(capturedAt=iso_minutes_ago(minutes)),
                           headers=HEADERS).get_json()
        assert body["status"] == "PENDING"
        ids.append(body["id"])
    assert platform.batches == []

    connectivity.online = True
    report = client.post("/api/v1/soil-readings/synchronizations").get_json()

    oldest_first = [ids[1], ids[2], ids[0]]
    assert platform.batches == [(7, oldest_first[:2]), (7, oldest_first[2:])]  # batch size 2
    assert report["synchronized"] == 3
    assert report["stillPending"] == 0
    statuses = {r["id"]: r["status"] for r in client.get("/api/v1/soil-readings").get_json()}
    assert set(statuses.values()) == {"SYNCHRONIZED"}


def test_unreachable_platform_keeps_readings_pending(client, platform):
    platform.results = [SubmissionResult(SubmissionOutcome.UNREACHABLE, "Platform unreachable")]
    body = client.post("/api/v1/soil-readings", json=reading(), headers=HEADERS).get_json()

    assert body["status"] == "PENDING"
    assert body["statusReason"] == "Platform unreachable"

    report = client.post("/api/v1/soil-readings/synchronizations").get_json()
    assert report["synchronized"] == 1


def test_platform_rejection_discards_the_batch(client, platform):
    platform.results = [SubmissionResult(SubmissionOutcome.REJECTED, "HTTP 400: invalid")]
    body = client.post("/api/v1/soil-readings", json=reading(), headers=HEADERS).get_json()
    assert body["status"] == "DISCARDED"
    assert body["statusReason"] == "HTTP 400: invalid"


def test_device_not_linked_yet_stays_pending_without_counting_as_server_error(client, platform):
    platform.results = [SubmissionResult(SubmissionOutcome.RETRY_LATER, "HTTP 404: No plot") for _ in range(3)]
    client.post("/api/v1/soil-readings", json=reading(), headers=HEADERS)
    client.post("/api/v1/soil-readings/synchronizations")
    client.post("/api/v1/soil-readings/synchronizations")

    pending = client.get("/api/v1/soil-readings?status=pending").get_json()
    assert len(pending) == 1
    assert pending[0]["statusReason"] == "HTTP 404: No plot"


def test_repeated_server_errors_give_up_after_the_limit(client, platform):
    platform.results = [SubmissionResult(SubmissionOutcome.RETRY_LATER, "HTTP 500: boom", server_error=True)
                        for _ in range(2)]
    client.post("/api/v1/soil-readings", json=reading(), headers=HEADERS)  # 1st server error
    report = client.post("/api/v1/soil-readings/synchronizations").get_json()  # 2nd → limit reached

    assert report["givenUp"] == 1
    discarded = client.get("/api/v1/soil-readings?status=DISCARDED").get_json()
    assert discarded[0]["statusReason"].endswith("(gave up)")


def test_one_failing_device_does_not_block_the_others(client, platform, connectivity):
    connectivity.online = False
    client.post("/api/v1/soil-readings", json=reading(), headers=HEADERS)
    client.post("/api/v1/soil-readings", json=reading(deviceId="OS-015"), headers={"X-API-Key": "other-key"})
    connectivity.online = True
    platform.results = [SubmissionResult(SubmissionOutcome.RETRY_LATER, "HTTP 404: No plot")]

    report = client.post("/api/v1/soil-readings/synchronizations").get_json()

    assert [device for device, _ in platform.batches] in ([7, 8], [8, 7])
    assert report["synchronized"] == 1
    assert report["stillPending"] == 1


def test_listing_filters_by_status_and_rejects_unknown_ones(client):
    client.post("/api/v1/soil-readings", json=reading(), headers=HEADERS)
    client.post("/api/v1/soil-readings", json=reading(conductivityDsM=-1), headers=HEADERS)

    assert len(client.get("/api/v1/soil-readings").get_json()) == 2
    assert len(client.get("/api/v1/soil-readings?status=discarded").get_json()) == 1
    assert client.get("/api/v1/soil-readings?status=lost").status_code == 400


def test_health_reports_connectivity_and_counts(client, connectivity):
    client.post("/api/v1/soil-readings", json=reading(), headers=HEADERS)
    connectivity.online = False

    body = client.get("/api/v1/health").get_json()

    assert body["status"] == "UP"
    assert body["platformReachable"] is False
    assert body["readings"]["SYNCHRONIZED"] == 1
    assert body["readings"]["PENDING"] == 0
