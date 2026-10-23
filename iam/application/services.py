"""Application services of the IAM context."""
from iam.domain.entities import Device
from iam.domain.services import AuthService, parse_device_spec
from iam.infrastructure.repositories import DeviceRepository


class AuthApplicationService:
    def __init__(self, repository: DeviceRepository | None = None):
        self._repository = repository or DeviceRepository()

    def register_devices(self, spec: str) -> list[Device]:
        """Loads the devices configured for this gateway (``EDGE_DEVICES``)."""
        devices = parse_device_spec(spec)
        for device in devices:
            self._repository.save(device)
        return devices

    def authenticate(self, activation_code: str | None, api_key: str | None) -> Device | None:
        """Returns the device when its code is known and the key matches; ``None`` otherwise."""
        if not activation_code:
            return None
        device = self._repository.find_by_code(activation_code)
        return device if AuthService.is_valid_key(device, api_key) else None
