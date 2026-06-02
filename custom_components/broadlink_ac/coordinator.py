"""Coordinator for Broadlink AC integration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
import logging
from typing import Any, Callable

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import BroadlinkACClient
from .const import DOMAIN
from .exceptions import BroadlinkACError

_LOGGER = logging.getLogger(__name__)

UPDATE_INTERVAL = timedelta(seconds=30)
_RECONNECT_AT_FAILURES = (5, 15, 30)
_UNAVAILABLE_AFTER_FAILURES = 10


@dataclass
class BroadlinkACDeviceData:
    """Runtime data for one Broadlink AC device."""

    client: BroadlinkACClient
    coordinator: BroadlinkACCoordinator


@dataclass
class BroadlinkACData:
    """Runtime data for a Broadlink AC config entry."""

    devices: list[BroadlinkACDeviceData]


class BroadlinkACCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinate updates for one Broadlink AC device."""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: BroadlinkACClient,
        host: str,
        mac: str,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN}_{mac.replace(':', '')}",
            update_interval=UPDATE_INTERVAL,
        )
        self.client = client
        self.host = host
        self.mac = mac
        self.mac_id = mac.replace(":", "")
        self._last_error_msg: str | None = None
        self._consecutive_failures: int = 0

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from the AC."""
        try:
            status = await self.hass.async_add_executor_job(self.client.get_ac_status)
        except BroadlinkACError as err:
            self._consecutive_failures += 1
            error_msg = str(err)

            if error_msg != self._last_error_msg:
                self._last_error_msg = error_msg
                _LOGGER.warning(
                    "Failed to communicate with Broadlink AC at %s "
                    "(failure #%d): %s",
                    self.host,
                    self._consecutive_failures,
                    err,
                )
            else:
                _LOGGER.debug(
                    "Still unable to reach Broadlink AC at %s "
                    "(failure #%d, unchanged): %s",
                    self.host,
                    self._consecutive_failures,
                    err,
                )

            if self._consecutive_failures in _RECONNECT_AT_FAILURES:
                reconnected = await self.hass.async_add_executor_job(
                    self.client.reconnect
                )
                if reconnected:
                    _LOGGER.info(
                        "Broadlink AC at %s reconnected", self.host
                    )
                    self._consecutive_failures = 0
                    self._last_error_msg = None
                    if self.data is not None:
                        return self.data
                else:
                    _LOGGER.warning(
                        "Broadlink AC at %s reconnection attempt failed", self.host
                    )

            if self._consecutive_failures > _UNAVAILABLE_AFTER_FAILURES:
                raise UpdateFailed(
                    f"Broadlink AC at {self.host} unreachable for "
                    f"{self._consecutive_failures} consecutive attempts"
                ) from err

            if self.data is not None:
                return self.data
            raise UpdateFailed(
                f"Failed to communicate with Broadlink AC: {err}"
            ) from err

        if self._consecutive_failures > 0:
            _LOGGER.info(
                "Broadlink AC at %s is back online after %d failures",
                self.host,
                self._consecutive_failures,
            )
        self._consecutive_failures = 0
        self._last_error_msg = None

        if not isinstance(status, dict):
            raise UpdateFailed("Failed to get Broadlink AC status")

        return status

    async def async_call(self, func: Callable[..., Any], *args: Any) -> Any:
        """Run a blocking AC command and update coordinator data."""
        try:
            result = await self.hass.async_add_executor_job(func, *args)
        except BroadlinkACError as err:
            raise HomeAssistantError(
                f"Failed to communicate with Broadlink AC: {err}"
            ) from err

        if isinstance(result, dict):
            self.async_set_updated_data(result)
        else:
            await self.async_request_refresh()

        return result
