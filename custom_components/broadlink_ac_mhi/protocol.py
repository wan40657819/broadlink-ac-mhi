"""Low-level Broadlink UDP protocol support."""

from __future__ import annotations

import random
import socket
import threading
import time

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from .exceptions import BroadlinkACTimeoutError

_INIT_KEY = "097628343fe99e23765c1513accf8b02"

# BroadLink DNA command words used by the MHI AC.
COMMAND_AUTH = 0x65
COMMAND_AC = 0x6A
COMMAND_AC_STATUS = 0x03EE

# MHI SmartHome AC framing sent over BroadLink DNA command 0x006A.
MHI_MODE_AUTO = 0
MHI_MODE_DRY = 1
MHI_MODE_COOL = 2
MHI_MODE_FAN = 3
MHI_MODE_HEAT = 4

MHI_FAN_LOW = 0
MHI_FAN_HIGH = 1
MHI_FAN_STRONG = 2
MHI_FAN_AUTO = 7

MHI_MIN_TEMPERATURE = 18.0
MHI_MAX_TEMPERATURE = 30.0

_MHI_FRAME_HEADER = b"\xA5\xA5\x5A\x5A\x00\x00\xFF\xFF\x14\x00\x00\x00"
_MHI_FRAME_PAYLOAD_PREFIX = b"\xA9\x00\x05"
_MHI_FRAME_PAYLOAD_SUFFIX = b"\xFB" + bytes(5) + b"\xFF\xFF\xFF\xFF" + b"\x0F\x00"
_MHI_CONTROL_PREFIX = b"\x20\x00"
_MHI_CONTROL_SUFFIX = bytes(14)
_MHI_GET_MODE = 0x80
_MHI_GET_FAN = 0x80
_MHI_GET_TEMPERATURE = 0x00


def mhi_checksum(data: bytes | bytearray) -> int:
    """Return the MHI additive checksum for the supplied bytes."""
    return sum(data) & 0xFFFF


def mhi_mode_byte(power: bool, mode: int) -> int:
    """Encode MHI mode byte as 0xA2 | power | (mode index << 2)."""
    return 0xA2 | (1 if power else 0) | ((mode & 0x07) << 2)


def mhi_fan_byte(level: int) -> int:
    """Encode MHI fan byte as 0x88 | fan level."""
    return 0x88 | (level & 0x07)


def mhi_temperature_byte(temperature: float) -> int:
    """Encode MHI setpoint byte as 0x80 | degrees Celsius * 2."""
    return 0x80 | (int(round(temperature * 2)) & 0x7F)


def build_mhi_frame(mode: int, fan: int, temperature: int) -> bytes:
    """Build the 32-byte MHI request frame from encoded state bytes."""
    payload = bytearray(_MHI_FRAME_PAYLOAD_PREFIX)
    payload += bytes((mode & 0xFF, fan & 0xFF, temperature & 0xFF))
    payload += _MHI_FRAME_PAYLOAD_SUFFIX
    payload += mhi_checksum(payload).to_bytes(2, "big")
    return _MHI_FRAME_HEADER + bytes(payload)


def build_mhi_get_frame() -> bytes:
    """Build the 32-byte MHI status-query frame used by the app."""
    return build_mhi_frame(_MHI_GET_MODE, _MHI_GET_FAN, _MHI_GET_TEMPERATURE)


def build_mhi_control_body(frame: bytes) -> bytes:
    """Wrap a 32-byte MHI frame in the 48-byte 0x006A request body."""
    if len(frame) != 32:
        raise ValueError("MHI frame must be 32 bytes")
    return _MHI_CONTROL_PREFIX + frame + _MHI_CONTROL_SUFFIX


def build_mhi_get_body() -> bytes:
    """Build the 48-byte 0x006A request body that queries AC state."""
    return build_mhi_control_body(build_mhi_get_frame())


def build_mhi_set_body(
    *,
    power: bool,
    mode: int,
    fan: int,
    temperature: float,
) -> bytes:
    """Build the 48-byte 0x006A request body that sets AC state."""
    if not MHI_MIN_TEMPERATURE <= temperature <= MHI_MAX_TEMPERATURE:
        raise ValueError(
            f"MHI temperature must be {MHI_MIN_TEMPERATURE:g}.."
            f"{MHI_MAX_TEMPERATURE:g} C"
        )
    frame = build_mhi_frame(
        mhi_mode_byte(power, mode),
        mhi_fan_byte(fan),
        mhi_temperature_byte(temperature),
    )
    return build_mhi_control_body(frame)


def parse_mhi_status(body: bytes | bytearray) -> dict[str, int | float | bool] | None:
    """Parse a 0x03EE response body, returning None when it is not valid."""
    if len(body) < 22 or body[0:2] != b"\x14\x00":
        return None

    status = bytes(body[2:22])
    if mhi_checksum(status[:18]) != int.from_bytes(status[18:20], "big"):
        return None

    return {
        "mode_byte": status[3],
        "power": bool(status[3] & 0x01),
        "mode": (status[3] >> 2) & 0x07,
        "fan_byte": status[4],
        "fan": status[4] & 0x07,
        "temperature_byte": status[5],
        "temperature": (status[5] & 0x7F) / 2,
        "indoor_raw": status[6],
        "error": status[7],
        "humidity": status[8],
        "outdoor_raw": status[9],
    }


class BroadlinkDeviceProtocol:
    """Low-level encrypted UDP transport for Broadlink devices."""

    def __init__(
        self,
        host: tuple[str, int],
        mac: bytes,
        timeout: int = 10,
        name: str | None = None,
        cloud: bool | None = None,
        devtype: int | None = None,
        update_interval: int = 0,
        bind_to_ip: str | None = None,
    ) -> None:
        """Initialize the protocol transport."""
        self.host = host
        self.mac = mac
        self.name = name
        self.cloud = cloud
        self.timeout = timeout
        self.devtype = devtype
        self.count = random.randrange(0xFFFF)
        self.key = bytearray(
            [
                0x09,
                0x76,
                0x28,
                0x34,
                0x3F,
                0xE9,
                0x9E,
                0x23,
                0x76,
                0x5C,
                0x15,
                0x13,
                0xAC,
                0xCF,
                0x8B,
                0x02,
            ]
        )
        self.iv = bytearray(
            [
                0x56,
                0x2E,
                0x17,
                0x99,
                0x6D,
                0x09,
                0x3D,
                0x28,
                0xDD,
                0xB3,
                0xBA,
                0x69,
                0x5A,
                0x2E,
                0x6F,
                0x58,
            ]
        )
        self.id = bytearray([0, 0, 0, 0])
        self.cs = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.cs.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.cs.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self.type = "Unknown"
        self.lock = threading.Lock()
        self.update_interval = update_interval
        self.bind_to_ip = bind_to_ip
        self.aes = None
        self.update_aes(bytes.fromhex(_INIT_KEY))

    def update_aes(self, key: bytes) -> None:
        """Update AES."""
        self.aes = Cipher(
            algorithms.AES(bytes(key)), modes.CBC(self.iv), backend=default_backend()
        )

    def encrypt(self, payload: bytes) -> bytes:
        """Encrypt the payload."""
        encryptor = self.aes.encryptor()
        return encryptor.update(bytes(payload)) + encryptor.finalize()

    def decrypt(self, payload: bytes) -> bytes:
        """Decrypt the payload."""
        decryptor = self.aes.decryptor()
        return decryptor.update(bytes(payload)) + decryptor.finalize()

    def close(self) -> None:
        """Close the device socket."""
        self.cs.close()

    def auth(self) -> bool:
        """Authenticate with the Broadlink device."""
        payload = bytearray(0x50)
        payload[0x04:0x13] = b"111111111111111"
        payload[0x1E] = 0x01
        payload[0x2D] = 0x01
        payload[0x30:0x37] = b"Test  1"

        response = self.send_packet(COMMAND_AUTH, payload)
        decrypted_payload = self.decrypt(bytes(response[0x38:]))

        if not decrypted_payload:
            return False

        key = decrypted_payload[0x04:0x14]
        if len(key) % 16 != 0:
            return False

        self.id = decrypted_payload[0x00:0x04]
        self.key = key
        self.update_aes(key)
        return True

    def get_type(self) -> str:
        """Return the device type string."""
        return self.type

    def send_packet(self, command: int, payload: bytes | bytearray) -> bytearray:
        """Send an encrypted Broadlink packet and return the raw response."""
        self.count = (self.count + 1) & 0xFFFF
        packet = bytearray(0x38)
        packet[0x00] = 0x5A
        packet[0x01] = 0xA5
        packet[0x02] = 0xAA
        packet[0x03] = 0x55
        packet[0x04] = 0x5A
        packet[0x05] = 0xA5
        packet[0x06] = 0xAA
        packet[0x07] = 0x55
        packet[0x24] = 0x2A
        packet[0x25] = 0x4E
        packet[0x26] = command
        packet[0x28] = self.count & 0xFF
        packet[0x29] = self.count >> 8
        packet[0x2A:0x30] = self.mac[0:6]
        packet[0x30:0x34] = self.id[0:4]

        packet_checksum = 0xBEAF
        for byte in payload:
            packet_checksum += byte
            packet_checksum &= 0xFFFF

        encrypted_payload = self.encrypt(bytes(payload))

        packet[0x34] = packet_checksum & 0xFF
        packet[0x35] = packet_checksum >> 8
        packet.extend(encrypted_payload)

        packet_checksum = 0xBEAF
        for byte in packet:
            packet_checksum += byte
            packet_checksum &= 0xFFFF
        packet[0x20] = packet_checksum & 0xFF
        packet[0x21] = packet_checksum >> 8

        starttime = time.time()
        with self.lock:
            while True:
                try:
                    self.cs.sendto(packet, self.host)
                    self.cs.settimeout(5)
                    response = self.cs.recvfrom(1024)
                    break
                except socket.timeout as err:
                    if (time.time() - starttime) < self.timeout:
                        continue
                    raise BroadlinkACTimeoutError(200, self.host) from err

        return bytearray(response[0])
