import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import create_app  # noqa: E402
from config import Settings  # noqa: E402
from monitoring.infrastructure.platform_sync_client import SubmissionOutcome, SubmissionResult  # noqa: E402

DEVICE_KEY = "os-014-device-key"
HEADERS = {"X-API-Key": DEVICE_KEY}


class FakePlatformClient:
    """Records each batch and answers with the queued results (ACCEPTED by default)."""

    def __init__(self):
        self.batches = []
        self.results = []

    def submit_batch(self, platform_device_id, readings):
        self.batches.append((platform_device_id, [r.id for r in readings]))
        if self.results:
            return self.results.pop(0)
        return SubmissionResult(SubmissionOutcome.ACCEPTED, platform_batch_id=len(self.batches),
                                accepted_count=len(readings), discarded_count=0)


class FakeConnectivity:
    def __init__(self):
        self.online = True

    def is_online(self):
        return self.online


@pytest.fixture
def platform():
    return FakePlatformClient()


@pytest.fixture
def connectivity():
    return FakeConnectivity()


@pytest.fixture
def app(tmp_path, platform, connectivity):
    settings = Settings(database_path=str(tmp_path / "edge.db"), sync_batch_size=2, max_server_errors=2,
                        devices=f"OS-014:7:{DEVICE_KEY},OS-015:8:other-key:1.1")
    return create_app(settings, platform_client=platform, connectivity_monitor=connectivity, start_scheduler=False)


@pytest.fixture
def client(app):
    return app.test_client()


def reading(**overrides):
    body = {"deviceId": "OS-014", "conductivityDsM": 2.0, "moisturePercent": 35.0, "temperatureCelsius": 25.0}
    body.update(overrides)
    return body
