"""Device repository over SQLite."""
from iam.domain.entities import Device
from iam.infrastructure.models import DeviceModel


class DeviceRepository:
    @staticmethod
    def find_by_code(activation_code: str) -> Device | None:
        model = DeviceModel.get_or_none(DeviceModel.activation_code == activation_code)
        if model is None:
            return None
        return Device(model.activation_code, model.platform_device_id, model.api_key, model.calibration_factor)

    @staticmethod
    def save(device: Device) -> None:
        DeviceModel.replace(
            activation_code=device.activation_code,
            platform_device_id=device.platform_device_id,
            api_key=device.api_key,
            calibration_factor=device.calibration_factor,
        ).execute()
