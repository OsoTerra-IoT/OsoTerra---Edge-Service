"""Edge Service settings, read from environment variables with local defaults."""
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_path: str = "ososense-edge.db"
    platform_base_url: str = "http://localhost:8080"
    # Shared key the platform expects in X-Edge-Api-Key. Local-only default.
    edge_api_key: str = "local-edge-key"
    # Devices this gateway serves: "code:platformDeviceId:deviceApiKey[:calibrationFactor]", comma-separated.
    devices: str = "OS-014:1:os-014-device-key"
    sync_interval_seconds: float = 30.0
    sync_batch_size: int = 50
    request_timeout_seconds: float = 5.0
    max_server_errors: int = 5
    # "local" sends capturedAt in the gateway's local time; "utc" in UTC (Railway runs in UTC).
    platform_timezone: str = "local"
    compensation_coefficient: float = 0.02
    host: str = "0.0.0.0"
    port: int = 5000

    @classmethod
    def from_env(cls) -> "Settings":
        env = os.environ.get
        return cls(
            database_path=env("EDGE_DATABASE_PATH", cls.database_path),
            platform_base_url=env("PLATFORM_BASE_URL", cls.platform_base_url).rstrip("/"),
            edge_api_key=env("EDGE_API_KEY", cls.edge_api_key),
            devices=env("EDGE_DEVICES", cls.devices),
            sync_interval_seconds=float(env("SYNC_INTERVAL_SECONDS", cls.sync_interval_seconds)),
            sync_batch_size=int(env("SYNC_BATCH_SIZE", cls.sync_batch_size)),
            request_timeout_seconds=float(env("REQUEST_TIMEOUT_SECONDS", cls.request_timeout_seconds)),
            max_server_errors=int(env("MAX_SERVER_ERRORS", cls.max_server_errors)),
            platform_timezone=env("PLATFORM_TIMEZONE", cls.platform_timezone),
            compensation_coefficient=float(env("COMPENSATION_COEFFICIENT", cls.compensation_coefficient)),
            host=env("EDGE_HOST", cls.host),
            port=int(env("EDGE_PORT", cls.port)),
        )
