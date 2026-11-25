"""MHI state mapping helpers for the Broadlink AC MHI integration."""

from __future__ import annotations

from typing import Any, Mapping

MIN_TEMPERATURE = 18.0
MAX_TEMPERATURE = 30.0

HVAC_MODES = ("off", "auto", "dry", "cool", "fan_only", "heat")
FAN_MODES = ("auto", "low", "high", "strong")

HVAC_MODE_TO_MHI_MODE = {
    "auto": 0,
    "dry": 1,
    "cool": 2,
    "fan_only": 3,
    "heat": 4,
}
MHI_MODE_TO_HVAC_MODE = {
    index: mode for mode, index in HVAC_MODE_TO_MHI_MODE.items()
}

FAN_MODE_TO_MHI_LEVEL = {
    "low": 0,
    "high": 1,
    "strong": 2,
    "auto": 7,
}
MHI_LEVEL_TO_FAN_MODE = {
    level: mode for mode, level in FAN_MODE_TO_MHI_LEVEL.items()
}

# Indoor sensor lookup from the MHI SmartHome APK
# (com.mitsubishielectric.smarthome.data.MitsubishiTempData). Status byte 6 of
# the 0x03EE reply is an index into this table, not a linear temperature.
MHI_INDOOR_TEMPERATURES: tuple[int, ...] = (
    -64, -64, -56, -51, -47, -44, -42, -40, -38, -36, -35, -33, -32, -31, -30, -28,
    -27, -26, -26, -25, -24, -23, -22, -21, -21, -20, -19, -19, -18, -17, -17, -16,
    -16, -15, -14, -14, -13, -13, -12, -12, -11, -11, -10, -10, -10, -9, -9, -8,
    -8, -7, -7, -6, -6, -6, -5, -5, -5, -4, -4, -3, -3, -3, -2, -2,
    -2, -1, -1, -1, 0, 0, 1, 1, 1, 2, 2, 2, 3, 3, 3, 3,
    4, 4, 4, 5, 5, 5, 6, 6, 6, 7, 7, 7, 7, 8, 8, 8,
    9, 9, 9, 9, 10, 10, 10, 10, 11, 11, 11, 12, 12, 12, 12, 13,
    13, 13, 14, 14, 14, 14, 15, 15, 15, 15, 16, 16, 16, 17, 17, 17,
    17, 18, 18, 18, 18, 19, 19, 19, 19, 20, 20, 20, 20, 21, 21, 21,
    21, 22, 22, 22, 22, 23, 23, 23, 23, 24, 24, 24, 24, 25, 25, 25,
    25, 26, 26, 26, 26, 27, 27, 27, 27, 28, 28, 28, 28, 29, 29, 29,
    29, 30, 30, 30, 30, 31, 31, 31, 31, 32, 32, 32, 33, 33, 33, 33,
    34, 34, 34, 34, 35, 35, 35, 35, 35, 36, 36, 36, 36, 37, 37, 37,
    38, 38, 38, 38, 39, 39, 39, 39, 40, 40, 40, 41, 41, 41, 41, 42,
    42, 42, 43, 43, 43, 44, 44, 44, 44, 45, 45, 45, 46, 46, 46, 47,
    47, 47, 47, 48, 48, 48, 49, 49, 49, 50, 50, 50, 51, 51, 51, 52,
)


def decode_indoor_temperature(raw: int) -> float | None:
    """Decode the indoor temperature sensor byte of an MHI status reply."""
    if raw <= 0 or raw >= len(MHI_INDOOR_TEMPERATURES):
        return None
    return float(MHI_INDOOR_TEMPERATURES[raw])


def default_status() -> dict[str, Any]:
    """Return the default MHI AC status."""
    return {
        "power": False,
        "hvac_mode": "auto",
        "fan_mode": "auto",
        "temperature": 25.0,
        "current_temperature": None,
        "humidity": None,
        "error": None,
        "macaddress": None,
        "hostip": None,
        "name": None,
        "lastupdate": 0,
    }


def status_from_mhi(
    parsed: Mapping[str, Any], base: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    """Convert a parsed MHI status frame into the integration status dict."""
    status = dict(base) if base is not None else default_status()

    status["power"] = bool(parsed["power"])
    status["hvac_mode"] = MHI_MODE_TO_HVAC_MODE.get(int(parsed["mode"]), "auto")
    status["fan_mode"] = MHI_LEVEL_TO_FAN_MODE.get(int(parsed["fan"]), "auto")
    status["temperature"] = float(parsed["temperature"])
    status["current_temperature"] = decode_indoor_temperature(int(parsed["indoor_raw"]))

    humidity = int(parsed["humidity"])
    status["humidity"] = humidity if humidity > 0 else None

    error = int(parsed["error"])
    status["error"] = error if error > 0 else None

    return status
