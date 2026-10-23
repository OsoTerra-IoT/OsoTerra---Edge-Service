"""OsoSense Edge Service: receives readings from the field devices, validates and compensates
them, buffers them in SQLite and synchronizes them with the OsoSense platform."""
import logging
from dataclasses import dataclass

from flask import Flask

from config import Settings
from health.interfaces.services import health_api
from iam.application.services import AuthApplicationService
from monitoring.application.services import CaptureReadingCommandHandler, SynchronizeBufferedReadingsCommandHandler
from monitoring.domain.services import TemperatureCompensationService
from monitoring.infrastructure.connectivity_monitor import ConnectivityMonitor
from monitoring.infrastructure.platform_sync_client import PlatformSyncClient
from monitoring.infrastructure.repositories import PeeweeSoilReadingRepository
from monitoring.infrastructure.scheduler import SyncScheduler
from monitoring.interfaces.services import monitoring_api
from shared.infrastructure.database import init_db


@dataclass
class EdgeServices:
    auth: AuthApplicationService
    readings: PeeweeSoilReadingRepository
    connectivity: ConnectivityMonitor
    synchronize: SynchronizeBufferedReadingsCommandHandler
    capture: CaptureReadingCommandHandler
    scheduler: SyncScheduler | None = None


def create_app(settings: Settings | None = None, platform_client=None, connectivity_monitor=None,
               start_scheduler: bool = True) -> Flask:
    settings = settings or Settings.from_env()
    init_db(settings.database_path)

    auth = AuthApplicationService()
    auth.register_devices(settings.devices)

    readings = PeeweeSoilReadingRepository()
    connectivity = connectivity_monitor or ConnectivityMonitor(settings.platform_base_url)
    client = platform_client or PlatformSyncClient(
        settings.platform_base_url, settings.edge_api_key,
        settings.request_timeout_seconds, settings.platform_timezone)
    synchronize = SynchronizeBufferedReadingsCommandHandler(
        readings, client, connectivity, settings.sync_batch_size, settings.max_server_errors)
    capture = CaptureReadingCommandHandler(
        readings, synchronize, compensation_service=TemperatureCompensationService(settings.compensation_coefficient))

    services = EdgeServices(auth, readings, connectivity, synchronize, capture)
    if start_scheduler:
        services.scheduler = SyncScheduler(synchronize.handle, settings.sync_interval_seconds)
        services.scheduler.start()

    app = Flask(__name__)
    app.extensions["ososense"] = services
    app.register_blueprint(monitoring_api)
    app.register_blueprint(health_api)
    return app


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    current = Settings.from_env()
    create_app(current).run(host=current.host, port=current.port)
