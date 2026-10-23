"""Domain services of the Soil Monitoring context (Edge side)."""
from datetime import datetime, timedelta

from monitoring.domain.value_objects import CompensationResult, SensorRange

REFERENCE_TEMPERATURE_CELSIUS = 25.0
# A device clock slightly ahead of the gateway's is tolerated; more than this is a bad timestamp.
CLOCK_SKEW_TOLERANCE = timedelta(minutes=1)


class ReadingValidationService:
    """Decides whether a reading is physically possible for the soil probe."""

    def __init__(
        self,
        conductivity_range: SensorRange = SensorRange(0.0, 20.0),
        moisture_range: SensorRange = SensorRange(0.0, 100.0),
        temperature_range: SensorRange = SensorRange(-10.0, 60.0),
    ):
        self.conductivity_range = conductivity_range
        self.moisture_range = moisture_range
        self.temperature_range = temperature_range

    def find_violation(
        self, conductivity_dsm: float, moisture_percentage: float, temperature_celsius: float | None,
        captured_at: datetime, now: datetime,
    ) -> str | None:
        """Returns why the reading is impossible, or ``None`` when it is valid."""
        if not self.conductivity_range.contains(conductivity_dsm):
            return f"Conductivity {conductivity_dsm} dS/m is outside {self._describe(self.conductivity_range)}"
        if not self.moisture_range.contains(moisture_percentage):
            return f"Moisture {moisture_percentage} % is outside {self._describe(self.moisture_range)}"
        if temperature_celsius is not None and not self.temperature_range.contains(temperature_celsius):
            return f"Temperature {temperature_celsius} °C is outside {self._describe(self.temperature_range)}"
        if captured_at > now + CLOCK_SKEW_TOLERANCE:
            return "A reading cannot be captured in the future"
        return None

    @staticmethod
    def _describe(sensor_range: SensorRange) -> str:
        return f"[{sensor_range.minimum}, {sensor_range.maximum}]"


class TemperatureCompensationService:
    """Refers electrical conductivity to 25 °C with the linear model EC25 = EC / (1 + α (T − 25)).

    The device's calibration factor (laboratory vs. device, from the platform's calibration
    records) multiplies the result.
    """

    def __init__(self, coefficient_per_celsius: float = 0.02):
        self.coefficient = coefficient_per_celsius

    def compensate(
        self, conductivity_dsm: float, temperature_celsius: float, calibration_factor: float = 1.0,
    ) -> CompensationResult:
        temperature_factor = 1.0 / (1.0 + self.coefficient * (temperature_celsius - REFERENCE_TEMPERATURE_CELSIUS))
        applied_factor = temperature_factor * calibration_factor
        return CompensationResult(
            raw_value=conductivity_dsm,
            compensated_value=round(conductivity_dsm * applied_factor, 3),
            applied_factor=round(applied_factor, 4),
        )
