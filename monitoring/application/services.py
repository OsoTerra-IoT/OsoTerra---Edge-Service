"""Use cases of the Soil Monitoring context that run in the Edge Service."""
import logging
import threading
from dataclasses import dataclass
from datetime import datetime, timezone

from iam.domain.entities import Device
from monitoring.domain.entities import SoilReading, SyncStatus
from monitoring.domain.services import ReadingValidationService, TemperatureCompensationService
from monitoring.infrastructure.platform_sync_client import SubmissionOutcome

logger = logging.getLogger(__name__)


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


@dataclass(frozen=True)
class CaptureReadingCommand:
    device: Device
    conductivity_dsm: float
    moisture_percentage: float
    temperature_celsius: float | None
    captured_at: datetime | None = None  # naive UTC; the gateway's clock when absent


@dataclass
class SyncReport:
    attempted: bool = False
    platform_reachable: bool | None = None
    synchronized: int = 0
    rejected: int = 0
    still_pending: int = 0
    given_up: int = 0


class SynchronizeBufferedReadingsCommandHandler:
    """Sends pending readings to the platform, oldest first, one batch per device at a time."""

    def __init__(self, repository, platform_client, connectivity_monitor,
                 batch_size: int = 50, max_server_errors: int = 5):
        self._repository = repository
        self._platform_client = platform_client
        self._connectivity_monitor = connectivity_monitor
        self._batch_size = batch_size
        self._max_server_errors = max_server_errors
        self._lock = threading.Lock()  # the request thread and the scheduler must not send twice

    def handle(self) -> SyncReport:
        report = SyncReport()
        if not self._lock.acquire(blocking=False):
            return report
        try:
            device_ids = self._repository.find_pending_platform_device_ids()
            if not device_ids:
                return report
            report.attempted = True
            report.platform_reachable = self._connectivity_monitor.is_online()
            if not report.platform_reachable:
                report.still_pending = self._repository.count_by_status()[SyncStatus.PENDING.value]
                return report
            for device_id in device_ids:
                if not self._synchronize_device(device_id, report):
                    break
            report.given_up = self._repository.discard_exhausted(self._max_server_errors)
            report.still_pending = self._repository.count_by_status()[SyncStatus.PENDING.value]
            return report
        finally:
            self._lock.release()

    def _synchronize_device(self, device_id: int, report: SyncReport) -> bool:
        """Returns ``False`` when the platform became unreachable and the cycle must stop."""
        while True:
            pending = self._repository.find_pending(device_id, self._batch_size)
            if not pending:
                return True
            ids = [reading.id for reading in pending]
            result = self._platform_client.submit_batch(device_id, pending)
            if result.outcome == SubmissionOutcome.ACCEPTED:
                self._repository.mark_synchronized(ids, result.platform_batch_id)
                report.synchronized += len(ids)
                logger.info("Batch %s for device %s: %s accepted, %s discarded by the platform",
                            result.platform_batch_id, device_id, result.accepted_count, result.discarded_count)
            elif result.outcome == SubmissionOutcome.REJECTED:
                self._repository.mark_discarded(ids, result.detail)
                report.rejected += len(ids)
            else:
                self._repository.record_failure(ids, result.detail, result.server_error)
                # Unreachable stops the whole cycle; any other failure only skips this device.
                return result.outcome != SubmissionOutcome.UNREACHABLE


class CaptureReadingCommandHandler:
    """Validates, compensates and stores a reading, then tries to transmit it right away."""

    def __init__(self, repository, synchronizer: SynchronizeBufferedReadingsCommandHandler | None,
                 validation_service: ReadingValidationService | None = None,
                 compensation_service: TemperatureCompensationService | None = None):
        self._repository = repository
        self._synchronizer = synchronizer
        self._validation = validation_service or ReadingValidationService()
        self._compensation = compensation_service or TemperatureCompensationService()

    def handle(self, command: CaptureReadingCommand) -> tuple[SoilReading, bool]:
        """Returns the stored reading and whether it is new (``False`` for a repeated capture)."""
        now = utc_now()
        captured_at = command.captured_at or now
        reading = SoilReading(
            device_code=command.device.activation_code,
            platform_device_id=command.device.platform_device_id,
            raw_conductivity_dsm=command.conductivity_dsm,
            moisture_percentage=command.moisture_percentage,
            temperature_celsius=command.temperature_celsius,
            captured_at=captured_at,
        )

        violation = self._validation.find_violation(
            command.conductivity_dsm, command.moisture_percentage, command.temperature_celsius, captured_at, now)
        if violation:
            reading.status, reading.status_reason = SyncStatus.DISCARDED, violation
            logger.warning("Reading from %s discarded: %s", reading.device_code, violation)
        elif command.temperature_celsius is None:
            reading.status = SyncStatus.UNCOMPENSATED
            reading.status_reason = "No temperature: stored raw, not sent to the platform"
        else:
            result = self._compensation.compensate(
                command.conductivity_dsm, command.temperature_celsius, command.device.calibration_factor)
            reading.compensated_conductivity_dsm = result.compensated_value
            reading.compensation_factor = result.applied_factor

        stored, created = self._repository.save(reading)
        if created and stored.status == SyncStatus.PENDING and self._synchronizer is not None:
            self._synchronizer.handle()
            stored = self._repository.find_by_id(stored.id)
        return stored, created
