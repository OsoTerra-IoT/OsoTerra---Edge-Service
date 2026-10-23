"""Domain services of the IAM context."""
import hmac

from iam.domain.entities import Device


class AuthService:
    """Checks the key a device presents, in constant time."""

    @staticmethod
    def is_valid_key(device: Device | None, api_key: str | None) -> bool:
        if device is None or not api_key:
            return False
        return hmac.compare_digest(device.api_key.encode(), api_key.encode())


def parse_device_spec(spec: str) -> list[Device]:
    """Parses ``code:platformDeviceId:apiKey[:calibrationFactor]`` entries separated by commas."""
    devices = []
    for entry in filter(None, (part.strip() for part in spec.split(","))):
        fields = entry.split(":")
        if len(fields) not in (3, 4):
            raise ValueError(f"Invalid device entry '{entry}': expected code:platformDeviceId:apiKey[:factor]")
        code, platform_id, api_key = fields[0], int(fields[1]), fields[2]
        factor = float(fields[3]) if len(fields) == 4 else 1.0
        if factor <= 0:
            raise ValueError(f"Calibration factor of '{code}' must be positive")
        devices.append(Device(code, platform_id, api_key, factor))
    return devices
