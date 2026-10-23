"""Tells whether the platform can be reached before trying to transmit."""
import socket
from urllib.parse import urlparse


class ConnectivityMonitor:
    def __init__(self, base_url: str, timeout_seconds: float = 2.0):
        parsed = urlparse(base_url)
        self._host = parsed.hostname or "localhost"
        self._port = parsed.port or (443 if parsed.scheme == "https" else 80)
        self._timeout = timeout_seconds
        self.last_known_online: bool | None = None

    def is_online(self) -> bool:
        try:
            with socket.create_connection((self._host, self._port), timeout=self._timeout):
                self.last_known_online = True
        except OSError:
            self.last_known_online = False
        return self.last_known_online
