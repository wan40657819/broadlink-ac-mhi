# MHI OEM-T1 Air-Conditioner UDP Protocol

This is the consolidated reference for the confirmed local UDP control path of
the Mitsubishi Heavy Industries air conditioner controlled by the BroadLink
OEM-T1 module (device type `0x4E97` / `20119`). 

Evidence is labelled so that confirmed wire behaviour is not confused with
assumptions.

## Confidence labels

- **Confirmed**: directly established by APK/native analysis, a validated
  capture, or a live request/reply.
- **Observed**: present in supplied captures or experiment logs but direction or
  semantics are not fully established.
- **Unresolved**: evidence is insufficient. Do not encode an assumption as a
  protocol rule.

## Application path

```text
AirConditioninfo
  -> MitsubishiDataPasers.AirConditionStatue(info) -> 32-byte MHI frame
  -> NetUnit.sendData
  -> dnaPassthrough(did, null, frame)
  -> NetworkAPI.dnaControl
  -> local UDP 80
```

`did` is the device ID; the sub-device argument is `null` for this AC. The APK
selects request command `0x006A` for device types above `0x2710` and configures
a 3000 ms local timeout, three sends and a 4-second probe interval.

## MHI inner frame

### Request format

**Confirmed:** the MHI frame is 32 bytes:

| Offset | Size | Bytes / meaning |
|---:|---:|---|
| `0x00` | 4 | `A5 A5 5A 5A` magic |
| `0x04` | 4 | `00 00 FF FF` |
| `0x08` | 4 | `14 00 00 00` (20-byte payload) |
| `0x0C` | 20 | Payload below |

| Payload offset | Value |
|---:|---|
| 0 | `A9` |
| 1 | `00` |
| 2 | `05` |
| 3 | mode byte |
| 4 | fan byte |
| 5 | setpoint byte |
| 6 | `FB` |
| 7..11 | `00 00 00 00 00` |
| 12..15 | `FF FF FF FF` |
| 16..17 | `0F 00` |
| 18..19 | Additive checksum, big-endian |

The inner checksum is `sum(payload[0:18]) & 0xFFFF`. No `0xBEAF` seed is used.

### 48-byte DNA control body

**Confirmed:** command `0x006A` carries:

```text
20 00 || 32-byte MHI frame || 00 00 00 00 00 00 00 00 00 00 00 00 00 00
```

The result is 48 bytes, an AES block. A status query uses sentinel state bytes
`80 80 00`:

```text
20 00 A5 A5 5A 5A 00 00 FF FF 14 00 00 00
A9 00 05 80 80 00 FB 00 00 00 00 00 FF FF FF FF 0F 00 06 B4
00 00 00 00 00 00 00 00 00 00 00 00 00 00
```

The app passes the bare 32-byte MHI frame into `dnaPassthrough`; the SDK/DNA
layer adds the `20 00` prefix and the 14 zero bytes.

### State bytes

```text
modeByte        = 0xA2 | power | (mode << 2)
temperatureByte = 0x80 | (degreesC * 2)
fanByte         = 0x88 | fan
```

`a.b.b.d.h.a.V(i, i2)` returns `i | 2 | ((i2 | 8) << 2) | 128`, which reduces to
the mode formula: `i` is the on/off bit, `i2` is the mode index.

| Mode index | Mode | | Fan level | Fan |
|---:|---|---|---:|---|
| 0 | Auto | | 0 | Low |
| 1 | Dry | | 1 | High |
| 2 | Cool | | 2 | Strong |
| 3 | Fan | | 7 | Auto |
| 4 | Heat | | | |

Examples: `AF 8F B2` = on, Fan, Auto fan, 25.0 °C. `A7 88 B2` = on, Dry, Low,
25.0 °C. `B3 88 B0` = on, Heat, Low, 24.0 °C. `B2 88 B0` = off, Heat, Low,
24.0 °C. The app normally allows 18..30 °C in 0.5 °C steps.

### Status response

**Confirmed:** command `0x03EE` returns a 32-byte plaintext body:

```text
14 00 || 20-byte status frame || 00 00 00 00 FF FF FF FF 0F 00
```

| Status offset | Meaning |
|---:|---|
| 0..2 | `6C 80 04` |
| 3 | mode byte (same encoding as request) |
| 4 | fan byte |
| 5 | setpoint byte |
| 6 | indoor temperature code |
| 7 | error code |
| 8 | humidity, percent |
| 9 | `tempOut` (raw; zero in all captures) |
| 10..11 | `00 00` |
| 12..15 | `FF FF FF FF` |
| 16..17 | `00 00` |
| 18..19 | additive checksum over bytes 0..17, big-endian |

**Confirmed sensor decoding:** status byte 6 is a lookup code, not the setpoint
formula. `MitsubishiTempData.getTempFromMap(0x9F)` returns **25 °C**. Status byte
8 is the humidity percentage: `0x42` = **66%**, `0x41` = 65%. The captured
indoor value stayed `0x9F` while humidity changed from 66% to 65%.

Example (Heat/on/Low, 25.0 °C setpoint, 66% humidity):

```text
6C 80 04 B3 88 B2 9F 00 42 00 00 00 FF FF FF FF 00 00 07 BA
```

The native `paraseAirCondition` mapping is:

```text
airConditionMode = byte[3]      errorCode = byte[7]
windSpeed        = byte[4]      humi      = byte[8]
tempeture        = byte[5]      tempOut   = byte[9]
tempSensor       = byte[6]
```

`tempOut` is parsed but was zero in every captured reply; its intended use is
unresolved.

## Local UDP transport

### Commands

| Purpose | Request | Reply |
|---|---|---|
| Discovery | `0x0006` | `0x0007` |
| Authentication | `0x0065` | `0x03E9` |
| AC control / status | `0x006A` | `0x03EE` |

In the captured transactions `reply = request + 0x0384` (the two 16-bit words
are little-endian on the wire).

### Packet envelope

**Confirmed:** a local control datagram is a 56-byte header followed by AES-CBC
ciphertext. The 48-byte body produces a 104-byte datagram.

| Offset | Size | Field |
|---:|---:|---|
| `0x00` | 8 | `5A A5 AA 55` repeated twice |
| `0x08` | 24 | Usually zero |
| `0x20` | 2 | Whole-packet checksum, little-endian |
| `0x22` | 2 | Device-specific; `0x0000` on accepted requests |
| `0x24` | 2 | Device type `0x4E97`, little-endian |
| `0x26` | 2 | Request command (`0x006A` for AC) |
| `0x28` | 2 | Counter, little-endian |
| `0x2A` | 6 | MAC, forward order (`E8 70 72 72 8C 22`) |
| `0x30` | 4 | Device ID, little-endian |
| `0x34` | 2 | Plaintext-body checksum, little-endian |
| `0x36` | 2 | Zero in observed packets |
| `0x38` | n | AES-128-CBC ciphertext |

### Authentication and crypto

**Confirmed:** `0x0065` returns `0x03E9`; the reply plaintext holds the device ID
at bytes 0..3 and the session key at bytes 4..0x13. The captured session key was
`9d1f7723a90d4347751b59692fdd95f3`. Control uses this session key.

Default BroadLink key and IV:

```text
key: 097628343fe99e23765c1513accf8b02
IV:  562e17996d093d28ddb3ba695a2e6f58
```

Both outer checksums use `(0xBEAF + sum(bytes)) & 0xFFFF`:

* Body checksum: over the decrypted plaintext, stored little-endian at `0x34`.
* Packet checksum: over the whole packet with bytes `0x20..0x21` zeroed, stored
  little-endian at `0x20`.

### Confirmed transaction and live verification

`tests/PCAPdroid_20261124_02_55_59.pcap` (1,059 frames, 82 seconds, official app
to AC on UDP port 80) shows GET and SET exchanges where the AC echoes the applied
state. A later capture switched through Dry, Cool and Heat and changed the
setpoint from 25.0 to 24.0 °C.

A live test on 2026-11-25 authenticated (device ID `1`), read back Heat/off/
24 °C, sent `B3 88 B2` (Heat/on/25 °C/Low), and read back the accepted state. A
second command `B2 88 B2` turned the unit off while preserving Heat/Low/25 °C.
All outer, body and inner checksums matched.

### Announcements and raw fields

**Observed:** AC announcements use 48-byte packets to broadcast UDP port 15001
with command `0x000E`; this is not the control destination. Outer `0x22` values
such as `0xFFF9`, `0xFFFC` and `0xFFFB` appear on other traffic; their meaning is
unresolved.

## Implementation notes

`custom_components/broadlink_ac/protocol.py` contains:

```python
build_mhi_frame()
build_mhi_get_body()
build_mhi_set_body(power=..., mode=..., fan=..., temperature=...)
parse_mhi_status(body)
```

The builders reproduce the captured local bodies byte-for-byte. `parse_mhi_status()`
returns `indoor_raw` / `outdoor_raw`; apply the `MitsubishiTempData` lookup in the
client. The integration's `client.py` still builds the older BroadLink `ac_db`
body, so wiring these builders into the climate entity remains pending.

## Remaining unknowns

1. Meaning of the outer `0x22` values (`0xFFF9`, `0xFFFC`, `0xFFFB`).
2. Relationship between the app's cookie key and the local auth session key.
3. Exact port reported by the native probe; UDP 80 is the confirmed control
   destination and 15001 is announcement traffic.
4. Purpose of the parsed-but-zero `tempOut` byte.
5. Half-degree setpoint behaviour; only whole-degree changes were observed.

Do not run high-rate command sweeps against the appliance. Earlier burst testing
left the module unresponsive until a physical power cycle.

