"""Tests for the MHI state mapping helpers."""

from __future__ import annotations

from custom_components.broadlink_ac_mhi.models import (
    FAN_MODE_TO_MHI_LEVEL,
    HVAC_MODE_TO_MHI_MODE,
    MHI_LEVEL_TO_FAN_MODE,
    MHI_MODE_TO_HVAC_MODE,
    decode_indoor_temperature,
    default_status,
    status_from_mhi,
)

PARSED_HEAT_ON = {
    "mode_byte": 0xB3,
    "power": True,
    "mode": 4,
    "fan_byte": 0x88,
    "fan": 0,
    "temperature_byte": 0xB2,
    "temperature": 25.0,
    "indoor_raw": 0x9F,
    "error": 0,
    "humidity": 66,
    "outdoor_raw": 0,
}


def test_mhi_mode_mapping_round_trips() -> None:
    """Test MHI mode index and HVAC mode name map to each other."""
    for hvac_mode, mhi_mode in HVAC_MODE_TO_MHI_MODE.items():
        assert MHI_MODE_TO_HVAC_MODE[mhi_mode] == hvac_mode


def test_mhi_fan_mapping_round_trips() -> None:
    """Test MHI fan level and fan mode name map to each other."""
    for fan_mode, level in FAN_MODE_TO_MHI_LEVEL.items():
        assert MHI_LEVEL_TO_FAN_MODE[level] == fan_mode


def test_decode_indoor_temperature_matches_captured_values() -> None:
    """Test the APK lookup table decodes the captured sensor bytes."""
    assert decode_indoor_temperature(0x9F) == 25.0
    assert decode_indoor_temperature(0x95) == 23.0
    assert decode_indoor_temperature(0x44) == 0.0


def test_decode_indoor_temperature_rejects_missing_sensor() -> None:
    """Test byte 0 means no reading."""
    assert decode_indoor_temperature(0) is None
    assert decode_indoor_temperature(-1) is None
    assert decode_indoor_temperature(256) is None


def test_status_from_mhi_maps_captured_heat_status() -> None:
    """Test a captured on/Heat/Low/25C status maps to the status dict."""
    status = status_from_mhi(PARSED_HEAT_ON)

    assert status["power"] is True
    assert status["hvac_mode"] == "heat"
    assert status["fan_mode"] == "low"
    assert status["temperature"] == 25.0
    assert status["current_temperature"] == 25.0
    assert status["humidity"] == 66
    assert status["error"] is None


def test_status_from_mhi_power_off_keeps_mode() -> None:
    """Test the mode is preserved when the AC is off."""
    parsed = dict(PARSED_HEAT_ON)
    parsed["power"] = False
    parsed["mode_byte"] = 0xB2

    status = status_from_mhi(parsed)

    assert status["power"] is False
    assert status["hvac_mode"] == "heat"


def test_status_from_mhi_falls_back_to_auto_for_unknown_values() -> None:
    """Test unknown mode or fan indices fall back to auto."""
    parsed = dict(PARSED_HEAT_ON)
    parsed["mode"] = 7
    parsed["fan"] = 5

    status = status_from_mhi(parsed)

    assert status["hvac_mode"] == "auto"
    assert status["fan_mode"] == "auto"


def test_status_from_mhi_preserves_base_metadata() -> None:
    """Test device metadata survives a status update."""
    base = default_status()
    base["macaddress"] = "e87072728c22"
    base["hostip"] = ("192.168.1.100", 80)

    status = status_from_mhi(PARSED_HEAT_ON, base=base)

    assert status["macaddress"] == "e87072728c22"
    assert status["hostip"] == ("192.168.1.100", 80)
