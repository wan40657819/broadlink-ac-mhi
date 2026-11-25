"""Climate platform for the Broadlink AC MHI integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.climate import (
    FAN_AUTO,
    FAN_HIGH,
    FAN_LOW,
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import BroadlinkACData, BroadlinkACCoordinator
from .entity import BroadlinkACEntity
from .models import (
    HVAC_MODE_TO_MHI_MODE,
    MAX_TEMPERATURE,
    MIN_TEMPERATURE,
)

FAN_STRONG = "strong"

SUPPORTED_FAN_MODES = [FAN_AUTO, FAN_LOW, FAN_HIGH, FAN_STRONG]
SUPPORTED_HVAC_MODES = [
    HVACMode.OFF,
    HVACMode.AUTO,
    HVACMode.COOL,
    HVACMode.HEAT,
    HVACMode.DRY,
    HVACMode.FAN_ONLY,
]


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Broadlink AC MHI climate entities from a config entry."""
    data: BroadlinkACData = entry.runtime_data
    async_add_entities(
        [BroadlinkACClimate(device.coordinator) for device in data.devices]
    )


class BroadlinkACClimate(BroadlinkACEntity, ClimateEntity):
    """Representation of a Broadlink AC MHI climate entity."""

    _attr_native_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.FAN_MODE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )
    _attr_hvac_modes = SUPPORTED_HVAC_MODES
    _attr_fan_modes = SUPPORTED_FAN_MODES
    _attr_min_temp = MIN_TEMPERATURE
    _attr_max_temp = MAX_TEMPERATURE
    _attr_target_temperature_step = 1.0

    def __init__(self, coordinator: BroadlinkACCoordinator) -> None:
        """Initialize the climate entity."""
        super().__init__(coordinator)
        self._attr_name = None
        self._attr_unique_id = f"{self._mac_id}_climate"
        self._attr_hvac_mode = HVACMode.OFF
        self._attr_fan_mode = FAN_AUTO
        self._attr_native_current_temperature = None
        self._attr_native_target_temperature = None
        self._update_attrs()

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._update_attrs()
        self.async_write_ha_state()

    def _update_attrs(self) -> None:
        """Update attributes from coordinator data."""
        status = self.coordinator.data
        if not isinstance(status, dict):
            return

        if status.get("power"):
            hvac_mode = status.get("hvac_mode", "auto")
            if hvac_mode not in HVAC_MODE_TO_MHI_MODE:
                hvac_mode = "auto"
            self._attr_hvac_mode = HVACMode(hvac_mode)
        else:
            self._attr_hvac_mode = HVACMode.OFF

        if fan_mode := status.get("fan_mode"):
            self._attr_fan_mode = fan_mode

        self._attr_native_current_temperature = status.get("current_temperature")
        self._attr_native_target_temperature = status.get("temperature")

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set the target temperature."""
        if (temperature := kwargs.get(ATTR_TEMPERATURE)) is not None:
            await self.coordinator.async_call(
                self.coordinator.client.set_temperature, temperature
            )

    async def async_turn_on(self) -> None:
        """Turn the AC on."""
        await self.coordinator.async_call(self.coordinator.client.switch_on)

    async def async_turn_off(self) -> None:
        """Turn the AC off."""
        await self.coordinator.async_call(self.coordinator.client.switch_off)

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set the HVAC mode."""
        await self.coordinator.async_call(
            self.coordinator.client.set_hvac_mode, hvac_mode.value
        )

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Set the fan mode."""
        await self.coordinator.async_call(
            self.coordinator.client.set_fan_mode, fan_mode
        )
