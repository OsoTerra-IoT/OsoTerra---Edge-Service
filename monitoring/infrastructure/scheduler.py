"""Background task that retries buffered readings on a fixed interval."""
import logging
import threading

logger = logging.getLogger(__name__)


class SyncScheduler:
    def __init__(self, synchronize, interval_seconds: float):
        self._synchronize = synchronize
        self._interval = interval_seconds
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="edge-sync", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        while not self._stop.wait(self._interval):
            try:
                report = self._synchronize()
                if report.attempted:
                    logger.info("Sync cycle: %s", report)
            except Exception:  # keep the loop alive whatever happens in one cycle
                logger.exception("Sync cycle failed")
