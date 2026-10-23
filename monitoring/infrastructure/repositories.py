"""Local soil reading repository over SQLite (PeeweeSoilReadingRepository in chapter 4)."""
from peewee import IntegrityError, fn

from monitoring.domain.entities import SoilReading, SyncStatus
from monitoring.infrastructure.models import SoilReadingModel


def _to_entity(model: SoilReadingModel) -> SoilReading:
    return SoilReading(
        id=model.id,
        device_code=model.device_code,
        platform_device_id=model.platform_device_id,
        raw_conductivity_dsm=model.raw_conductivity_dsm,
        compensated_conductivity_dsm=model.compensated_conductivity_dsm,
        compensation_factor=model.compensation_factor,
        moisture_percentage=model.moisture_percentage,
        temperature_celsius=model.temperature_celsius,
        captured_at=model.captured_at,
        status=SyncStatus(model.status),
        status_reason=model.status_reason,
        platform_batch_id=model.platform_batch_id,
        server_errors=model.server_errors,
    )


class PeeweeSoilReadingRepository:
    def save(self, reading: SoilReading) -> tuple[SoilReading, bool]:
        """Stores a new reading. Returns ``(reading, created)``; a repeated capture returns the stored one."""
        try:
            model = SoilReadingModel.create(
                device_code=reading.device_code,
                platform_device_id=reading.platform_device_id,
                raw_conductivity_dsm=reading.raw_conductivity_dsm,
                compensated_conductivity_dsm=reading.compensated_conductivity_dsm,
                compensation_factor=reading.compensation_factor,
                moisture_percentage=reading.moisture_percentage,
                temperature_celsius=reading.temperature_celsius,
                captured_at=reading.captured_at,
                status=reading.status.value,
                status_reason=reading.status_reason,
            )
            return _to_entity(model), True
        except IntegrityError:
            existing = SoilReadingModel.get(
                (SoilReadingModel.platform_device_id == reading.platform_device_id)
                & (SoilReadingModel.captured_at == reading.captured_at)
            )
            return _to_entity(existing), False

    def find_by_id(self, reading_id: int) -> SoilReading | None:
        model = SoilReadingModel.get_or_none(SoilReadingModel.id == reading_id)
        return _to_entity(model) if model else None

    def find_pending_platform_device_ids(self) -> list[int]:
        query = (SoilReadingModel
                 .select(SoilReadingModel.platform_device_id)
                 .where(SoilReadingModel.status == SyncStatus.PENDING.value)
                 .distinct())
        return [row.platform_device_id for row in query]

    def find_pending(self, platform_device_id: int, limit: int) -> list[SoilReading]:
        """Oldest pending readings first, so the platform receives them in chronological order."""
        query = (SoilReadingModel
                 .select()
                 .where((SoilReadingModel.status == SyncStatus.PENDING.value)
                        & (SoilReadingModel.platform_device_id == platform_device_id))
                 .order_by(SoilReadingModel.captured_at, SoilReadingModel.id)
                 .limit(limit))
        return [_to_entity(model) for model in query]

    def find_latest(self, status: SyncStatus | None = None, limit: int = 50) -> list[SoilReading]:
        query = SoilReadingModel.select().order_by(SoilReadingModel.captured_at.desc()).limit(limit)
        if status is not None:
            query = query.where(SoilReadingModel.status == status.value)
        return [_to_entity(model) for model in query]

    def count_by_status(self) -> dict[str, int]:
        counts = {status.value: 0 for status in SyncStatus}
        query = (SoilReadingModel
                 .select(SoilReadingModel.status, fn.COUNT(SoilReadingModel.id).alias("total"))
                 .group_by(SoilReadingModel.status))
        for row in query:
            counts[row.status] = row.total
        return counts

    def mark_synchronized(self, reading_ids: list[int], platform_batch_id: int | None) -> None:
        (SoilReadingModel
         .update(status=SyncStatus.SYNCHRONIZED.value, platform_batch_id=platform_batch_id, status_reason=None)
         .where(SoilReadingModel.id.in_(reading_ids))
         .execute())

    def mark_discarded(self, reading_ids: list[int], reason: str) -> None:
        (SoilReadingModel
         .update(status=SyncStatus.DISCARDED.value, status_reason=reason[:255])
         .where(SoilReadingModel.id.in_(reading_ids))
         .execute())

    def record_failure(self, reading_ids: list[int], reason: str, server_error: bool) -> None:
        """Keeps the readings pending and remembers why the last attempt failed."""
        changes = {SoilReadingModel.status_reason: reason[:255]}
        if server_error:
            changes[SoilReadingModel.server_errors] = SoilReadingModel.server_errors + 1
        SoilReadingModel.update(changes).where(SoilReadingModel.id.in_(reading_ids)).execute()

    def discard_exhausted(self, max_server_errors: int) -> int:
        """Gives up on pending readings the platform failed to process too many times."""
        return (SoilReadingModel
                .update(status=SyncStatus.DISCARDED.value,
                        status_reason=fn.COALESCE(SoilReadingModel.status_reason, "").concat(" (gave up)"))
                .where((SoilReadingModel.status == SyncStatus.PENDING.value)
                       & (SoilReadingModel.server_errors >= max_server_errors))
                .execute())
