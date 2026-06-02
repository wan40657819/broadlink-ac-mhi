"""Sensor platform for Broadlink AC integration."""

from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import BroadlinkACData, BroadlinkACCoordinator
from .entity import BroadlinkACEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Broadlink AC sensor entities from a config entry."""
    data: BroadlinkACData = entry.runtime_data
    async_add_entities(
        [
            BroadlinkACTemperatureSensor(device.coordinator)
            for device in data.devices
        ]
    )


class BroadlinkACTemperatureSensor(BroadlinkACEntity, SensorEntity):
    """Representation of the AC ambient temperature sensor."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_translation_key = "temperature"

    def __init__(self, coordinator: BroadlinkACCoordinator) -> None:
        """Initialize the temperature sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{self._mac_id}_temperature"
        self._attr_native_value = None
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
        self._attr_native_value = status.get("ambient_temp")
