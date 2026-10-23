"""Domain entities of the IAM context: the field devices this gateway accepts telemetry from."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Device:
    """A soil sensor known to the gateway.

    ``activation_code`` is the code printed on the device (``OS-014``) and the one the
    firmware sends; ``platform_device_id`` is the numeric id the platform assigned when the
    producer linked the sensor to a plot in the Web App.
    """

    activation_code: str
    platform_device_id: int
    api_key: str
    calibration_factor: float = 1.0
