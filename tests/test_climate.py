"""Tests for the Broadlink AC MHI climate entity."""

from __future__ import annotations

from unittest.mock import Mock

from homeassistant.components.climate import ClimateEntityFeature, HVACMode
from homeassistant.const import CONF_HOST, CONF_MAC
from homeassistant.core import HomeAssistant

from custom_components.broadlink_ac_mhi.climate import BroadlinkACClimate
from custom_components.broadlink_ac_mhi.const import DOMAIN
from custom_components.broadlink_ac_mhi.coordinator import BroadlinkACCoordinator
from pytest_homeassistant_custom_component.common import MockConfigEntry

HOST = "192.168.1.100"
MAC_FORMATTED = "34:ea:34:f7:58:66"
STATUS = {
    "power": True,
    "hvac_mode": "heat",
    "fan_mode": "low",
    "temperature": 25.0,
    "current_temperature": 25.0,
    "humidity": 66,
}


def _coordinator(
    hass: HomeAssistant, status: dict | None = STATUS
) -> tuple[Mock, BroadlinkACClimate]:
    """Create a climate entity with a mocked client."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: HOST, CONF_MAC: MAC_FORMATTED},
        unique_id=MAC_FORMATTED,
    )
    entry.add_to_hass(hass)
    client = Mock()
    client.switch_on.return_value = STATUS
    client.switch_off.return_value = STATUS
    client.set_hvac_mode.return_value = STATUS
    client.set_fan_mode.return_value = STATUS
    client.set_temperature.return_value = STATUS
    coordinator = BroadlinkACCoordinator(hass, entry, client, HOST, MAC_FORMATTED)
    coordinator.data = status
    return client, BroadlinkACClimate(coordinator)


async def test_climate_exposes_turn_on_off_features(hass: HomeAssistant) -> None:
    """Test climate entity supports turn_on and turn_off for assistants."""
    _, climate = _coordinator(hass)

    assert climate.supported_features & ClimateEntityFeature.TURN_ON
    assert climate.supported_features & ClimateEntityFeature.TURN_OFF


async def test_climate_has_no_unsupported_features(hass: HomeAssistant) -> None:
    """Test swing control is not advertised."""
    _, climate = _coordinator(hass)

    assert climate.supported_features & ClimateEntityFeature.FAN_MODE
    assert not climate.supported_features & ClimateEntityFeature.SWING_MODE


async def test_climate_temperature_step_is_one_degree(hass: HomeAssistant) -> None:
    """Test the target temperature changes in whole degrees."""
    _, climate = _coordinator(hass)

    assert climate.min_temp == 18.0
    assert climate.max_temp == 30.0
    assert climate.target_temperature_step == 1.0


async def test_climate_turn_off_calls_switch_off(hass: HomeAssistant) -> None:
    """Test turn_off uses the device power off command."""
    client, climate = _coordinator(hass)

    await climate.async_turn_off()

    client.switch_off.assert_called_once()


async def test_climate_turn_on_calls_switch_on(hass: HomeAssistant) -> None:
    """Test turn_on uses the device power on command."""
    client, climate = _coordinator(hass)

    await climate.async_turn_on()

    client.switch_on.assert_called_once()


async def test_climate_set_hvac_mode_off(hass: HomeAssistant) -> None:
    """Test setting HVAC mode OFF uses the mode handler."""
    client, climate = _coordinator(hass)

    await climate.async_set_hvac_mode(HVACMode.OFF)

    client.set_hvac_mode.assert_called_once_with("off")


async def test_climate_set_hvac_mode_heat(hass: HomeAssistant) -> None:
    """Test setting HVAC mode HEAT uses the mode handler."""
    client, climate = _coordinator(hass)

    await climate.async_set_hvac_mode(HVACMode.HEAT)

    client.set_hvac_mode.assert_called_once_with("heat")


async def test_climate_set_fan_mode(hass: HomeAssistant) -> None:
    """Test setting the fan mode uses the fan handler."""
    client, climate = _coordinator(hass)

    await climate.async_set_fan_mode("low")

    client.set_fan_mode.assert_called_once_with("low")


async def test_climate_set_temperature(hass: HomeAssistant) -> None:
    """Test setting the target temperature."""
    client, climate = _coordinator(hass)

    await climate.async_set_temperature(temperature=25.0)

    client.set_temperature.assert_called_once_with(25.0)


async def test_climate_maps_status_to_attributes(hass: HomeAssistant) -> None:
    """Test the MHI status maps to climate attributes."""
    _, climate = _coordinator(hass)

    assert climate.hvac_mode == HVACMode.HEAT
    assert climate.fan_mode == "low"
    assert climate.native_target_temperature == 25.0
    assert climate.native_current_temperature == 25.0


async def test_climate_power_off_reports_off_mode(hass: HomeAssistant) -> None:
    """Test a powered off AC reports the OFF HVAC mode."""
    off_status = dict(STATUS)
    off_status["power"] = False
    _, climate = _coordinator(hass, status=off_status)

    assert climate.hvac_mode == HVACMode.OFF
