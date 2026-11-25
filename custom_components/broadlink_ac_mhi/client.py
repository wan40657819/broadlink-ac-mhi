"""Client for MHI air conditioners behind a Broadlink OEM-T1 module."""

from __future__ import annotations

import logging
import socket
import threading
import time
from typing import Any

from .exceptions import BroadlinkACConnectionError
from .models import (
    FAN_MODE_TO_MHI_LEVEL,
    HVAC_MODE_TO_MHI_MODE,
    default_status,
    status_from_mhi,
)
from .protocol import (
    COMMAND_AC,
    COMMAND_AC_STATUS,
    BroadlinkDeviceProtocol,
    build_mhi_get_body,
    build_mhi_set_body,
    parse_mhi_status,
)

_LOGGER = logging.getLogger(__name__)


class BroadlinkACClient(BroadlinkDeviceProtocol):
    """Client for MHI air conditioners on Broadlink OEM-T1 modules."""

    type = "mhi"

    def __init__(
        self,
        host: tuple[str, int],
        mac: bytes,
        name: str | None = None,
        cloud: bool | None = None,
        update_interval: int = 0,
        devtype: int | None = None,
        bind_to_ip: str | None = None,
    ) -> None:
        """Initialize the MHI AC client and authenticate with the module."""
        super().__init__(
            host,
            mac,
            timeout=10,
            name=name,
            cloud=cloud,
            devtype=devtype,
            update_interval=update_interval,
            bind_to_ip=bind_to_ip,
        )

        self.status: dict[str, Any] = default_status()
        self.logger = _LOGGER
        self.operation_lock = threading.RLock()
        self.status["macaddress"] = "".join(format(x, "02x") for x in mac)
        self.status["hostip"] = host
        self.status["name"] = name
        self.status["lastupdate"] = 0

        self.logger.debug("Authenticating with Broadlink AC MHI")
        try:
            if self.auth() is False:
                raise BroadlinkACConnectionError("Authentication failed")
        except BroadlinkACConnectionError:
            self.close()
            raise

        self.logger.debug("Broadlink AC MHI authenticated")

    def reconnect(self) -> bool:
        """Close the socket and re-authenticate with the device."""
        self.logger.debug("Reconnecting to Broadlink AC MHI at %s", self.host)
        try:
            self.close()
        except Exception:
            pass

        self.cs = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.cs.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.cs.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

        try:
            return self.auth()
        except BroadlinkACConnectionError:
            return False

    def get_ac_status(self, force_update: bool = False) -> dict[str, Any]:
        """Get the current AC status."""
        with self.operation_lock:
            if (
                force_update is False
                and (self.status["lastupdate"] + self.update_interval) > time.time()
            ):
                return dict(self.status)
            return dict(self._request_status())

    def set_temperature(self, temperature: float) -> dict[str, Any]:
        """Set the target temperature."""
        self.logger.debug("Setting temperature to %s", temperature)
        return self._set_state(temperature=float(temperature))

    def set_hvac_mode(self, hvac_mode: str) -> dict[str, Any]:
        """Set the HVAC mode, turning the AC on or off as needed."""
        self.logger.debug("Setting HVAC mode to %s", hvac_mode)
        if hvac_mode == "off":
            return self._set_state(power=False)
        if hvac_mode not in HVAC_MODE_TO_MHI_MODE:
            raise ValueError(f"Unsupported HVAC mode: {hvac_mode}")
        return self._set_state(power=True, hvac_mode=hvac_mode)

    def set_fan_mode(self, fan_mode: str) -> dict[str, Any]:
        """Set the fan mode."""
        self.logger.debug("Setting fan mode to %s", fan_mode)
        if fan_mode not in FAN_MODE_TO_MHI_LEVEL:
            raise ValueError(f"Unsupported fan mode: {fan_mode}")
        return self._set_state(fan_mode=fan_mode)

    def switch_on(self) -> dict[str, Any]:
        """Switch the AC on."""
        self.logger.debug("Switching the AC on")
        return self._set_state(power=True)

    def switch_off(self) -> dict[str, Any]:
        """Switch the AC off."""
        self.logger.debug("Switching the AC off")
        return self._set_state(power=False)

    def _request_status(self) -> dict[str, Any]:
        """Query the AC and store the returned status frame."""
        response = self.send_packet(COMMAND_AC, build_mhi_get_body())

        command = int.from_bytes(response[0x26:0x28], "little")
        if command != COMMAND_AC_STATUS:
            raise BroadlinkACConnectionError(
                f"Unexpected reply command: 0x{command:04X}"
            )

        parsed = parse_mhi_status(self.decrypt(bytes(response[0x38:])))
        if parsed is None:
            raise BroadlinkACConnectionError("Invalid status response")

        self.logger.debug("MHI status: %s", parsed)
        self.status = status_from_mhi(parsed, base=self.status)
        self.status["lastupdate"] = time.time()
        return self.status

    def _set_state(
        self,
        power: bool | None = None,
        hvac_mode: str | None = None,
        fan_mode: str | None = None,
        temperature: float | None = None,
    ) -> dict[str, Any]:
        """Write a new state to the AC and read back the accepted status."""
        with self.operation_lock:
            # Refresh first so unchanged fields reflect the real device state.
            self._request_status()

            status = dict(self.status)
            if power is not None:
                status["power"] = bool(power)
            if hvac_mode is not None:
                if hvac_mode not in HVAC_MODE_TO_MHI_MODE:
                    raise ValueError(f"Unsupported HVAC mode: {hvac_mode}")
                status["hvac_mode"] = hvac_mode
            if fan_mode is not None:
                if fan_mode not in FAN_MODE_TO_MHI_LEVEL:
                    raise ValueError(f"Unsupported fan mode: {fan_mode}")
                status["fan_mode"] = fan_mode
            if temperature is not None:
                status["temperature"] = float(temperature)

            body = build_mhi_set_body(
                power=bool(status["power"]),
                mode=HVAC_MODE_TO_MHI_MODE[status["hvac_mode"]],
                fan=FAN_MODE_TO_MHI_LEVEL[status["fan_mode"]],
                temperature=float(status["temperature"]),
            )
            response = self.send_packet(COMMAND_AC, body)

            command = int.from_bytes(response[0x26:0x28], "little")
            if command != COMMAND_AC_STATUS:
                raise BroadlinkACConnectionError(
                    f"Unexpected set status reply command: 0x{command:04X}"
                )

            parsed = parse_mhi_status(self.decrypt(bytes(response[0x38:])))
            if parsed is None:
                raise BroadlinkACConnectionError("Invalid set status response")

            self.logger.debug("MHI set status reply: %s", parsed)
            self.status = status_from_mhi(parsed, base=self.status)
            self.status["lastupdate"] = time.time()
            return dict(self.status)
