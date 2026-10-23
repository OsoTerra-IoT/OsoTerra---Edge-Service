from datetime import datetime, timedelta

import pytest

from iam.domain.services import AuthService, parse_device_spec
from monitoring.domain.services import ReadingValidationService, TemperatureCompensationService

NOW = datetime(2026, 10, 19, 15, 0, 0)


class TestTemperatureCompensation:
    def test_reading_at_reference_temperature_is_unchanged(self):
        result = TemperatureCompensationService().compensate(2.0, 25.0)
        assert result.compensated_value == 2.0
        assert result.applied_factor == 1.0
        assert result.raw_value == 2.0

    def test_warmer_soil_lowers_the_conductivity(self):
        result = TemperatureCompensationService().compensate(2.2, 30.0)
        assert result.compensated_value == pytest.approx(2.0, abs=0.001)
        assert result.applied_factor == pytest.approx(1 / 1.1, abs=0.0001)

    def test_colder_soil_raises_the_conductivity(self):
        result = TemperatureCompensationService().compensate(1.8, 20.0)
        assert result.compensated_value == pytest.approx(2.0, abs=0.001)

    def test_calibration_factor_multiplies_the_result(self):
        result = TemperatureCompensationService().compensate(2.0, 25.0, calibration_factor=1.1)
        assert result.compensated_value == pytest.approx(2.2)
        assert result.applied_factor == pytest.approx(1.1)


class TestReadingValidation:
    @pytest.mark.parametrize("ec, moisture, temperature, expected", [
        (-0.1, 30, 25, "Conductivity"),
        (20.5, 30, 25, "Conductivity"),
        (2.0, -1, 25, "Moisture"),
        (2.0, 100.5, 25, "Moisture"),
        (2.0, 30, -127, "Temperature"),
        (2.0, 30, 61, "Temperature"),
    ])
    def test_physically_impossible_values_are_reported(self, ec, moisture, temperature, expected):
        violation = ReadingValidationService().find_violation(ec, moisture, temperature, NOW, NOW)
        assert violation.startswith(expected)

    def test_values_on_the_limits_are_valid(self):
        validation = ReadingValidationService()
        assert validation.find_violation(0.0, 0.0, -10.0, NOW, NOW) is None
        assert validation.find_violation(20.0, 100.0, 60.0, NOW, NOW) is None

    def test_missing_temperature_is_not_a_range_violation(self):
        assert ReadingValidationService().find_violation(2.0, 30, None, NOW, NOW) is None

    def test_future_capture_is_rejected_beyond_the_clock_tolerance(self):
        validation = ReadingValidationService()
        assert validation.find_violation(2.0, 30, 25, NOW + timedelta(seconds=30), NOW) is None
        assert "future" in validation.find_violation(2.0, 30, 25, NOW + timedelta(minutes=5), NOW)


class TestDeviceSpec:
    def test_parses_codes_ids_keys_and_optional_factor(self):
        devices = parse_device_spec("OS-014:1:key-a, OS-015:2:key-b:1.08")
        assert [(d.activation_code, d.platform_device_id, d.api_key, d.calibration_factor) for d in devices] == [
            ("OS-014", 1, "key-a", 1.0), ("OS-015", 2, "key-b", 1.08)]

    @pytest.mark.parametrize("spec", ["OS-014:1", "OS-014:x:key", "OS-014:1:key:0"])
    def test_rejects_malformed_entries(self, spec):
        with pytest.raises(ValueError):
            parse_device_spec(spec)

    def test_key_check_needs_device_and_matching_key(self):
        device = parse_device_spec("OS-014:1:secret")[0]
        assert AuthService.is_valid_key(device, "secret")
        assert not AuthService.is_valid_key(device, "wrong")
        assert not AuthService.is_valid_key(device, None)
        assert not AuthService.is_valid_key(None, "secret")
