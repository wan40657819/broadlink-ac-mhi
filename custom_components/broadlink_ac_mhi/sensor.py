"""Sensor platform for the Broadlink AC MHI integration."""

from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import BroadlinkACData, BroadlinkACCoordinator
from .entity import BroadlinkACEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Broadlink AC MHI sensor entities from a config entry."""
    data: BroadlinkACData = entry.runtime_data
    entities: list[SensorEntity] = []
    for device in data.devices:
        entities.append(BroadlinkACTemperatureSensor(device.coordinator))
        entities.append(BroadlinkACHumiditySensor(device.coordinator))
    async_add_entities(entities)


class BroadlinkACTemperatureSensor(BroadlinkACEntity, SensorEntity):
    """Representation of the AC indoor temperature sensor."""

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
        self._attr_native_value = status.get("current_temperature")


class BroadlinkACHumiditySensor(BroadlinkACEntity, SensorEntity):
    """Representation of the AC indoor humidity sensor."""

    _attr_device_class = SensorDeviceClass.HUMIDITY
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_translation_key = "humidity"

    def __init__(self, coordinator: BroadlinkACCoordinator) -> None:
        """Initialize the humidity sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{self._mac_id}_humidity"
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
        self._attr_native_value = status.get("humidity")
