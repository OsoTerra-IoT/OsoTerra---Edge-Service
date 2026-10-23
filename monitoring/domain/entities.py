"""Domain entities of the Soil Monitoring context (Edge side)."""
from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class SyncStatus(str, Enum):
    PENDING = "PENDING"              # validated and compensated, waiting to reach the platform
    SYNCHRONIZED = "SYNCHRONIZED"    # confirmed by the platform
    DISCARDED = "DISCARDED"          # out of range or rejected by the platform; never sent again
    UNCOMPENSATED = "UNCOMPENSATED"  # no temperature: raw value kept locally, not sent


@dataclass
class SoilReading:
    """One reading captured by a field device, with its raw and compensated conductivity.

    ``captured_at`` is a naive UTC datetime.
    """

    device_code: str
    platform_device_id: int
    raw_conductivity_dsm: float
    moisture_percentage: float
    temperature_celsius: float | None
    captured_at: datetime
    compensated_conductivity_dsm: float | None = None
    compensation_factor: float | None = None
    status: SyncStatus = SyncStatus.PENDING
    status_reason: str | None = None
    platform_batch_id: int | None = None
    server_errors: int = 0
    id: int | None = None

    def is_compensated(self) -> bool:
        return self.compensated_conductivity_dsm is not None
