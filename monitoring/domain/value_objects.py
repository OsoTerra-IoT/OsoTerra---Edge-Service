"""Value objects of the Soil Monitoring context (Edge side)."""
from dataclasses import dataclass


@dataclass(frozen=True)
class SensorRange:
    """Physical limits a sensor can report; anything outside is not a real measurement."""

    minimum: float
    maximum: float

    def contains(self, value: float) -> bool:
        return self.minimum <= value <= self.maximum


@dataclass(frozen=True)
class CompensationResult:
    """Raw value, value referred to 25 °C and the factor applied, kept together for traceability."""

    raw_value: float
    compensated_value: float
    applied_factor: float
