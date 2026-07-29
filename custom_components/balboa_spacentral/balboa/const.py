"""Protocol constants for Balboa Water Group spa controllers.

Every value here is either taken from the published protocol notes of
ccutrer/balboa_worldwide_app or confirmed against captures recorded from a real
controller (see fixtures/ and docs/10-phase0-ergebnis.md).
"""

from __future__ import annotations

from enum import Enum, IntEnum, StrEnum

# ── Framing ───────────────────────────────────────────────────────────────────
DELIMITER = 0x7E
CRC_POLYNOMIAL = 0x07
CRC_INIT = 0x02
CRC_FINAL_XOR = 0x02

#: Smallest sensible frame: delimiter, length, channel, 0xBF, type, crc, delimiter.
MIN_FRAME_LENGTH = 3
#: Nothing legitimate comes close; anything larger means we lost sync.
MAX_FRAME_LENGTH = 64

# ── Channels ──────────────────────────────────────────────────────────────────
#: Channel this client transmits as. The controller answers requests from it even
#: though it never polls it -- measured in phase 0.
CLIENT_CHANNEL = 0x0A
#: Broadcast channel used for status updates.
BROADCAST_CHANNEL = 0xFF
#: Channel of the "new client, you may register" invitation.
NEW_CLIENT_CHANNEL = 0xFE


class MessageType(bytes, Enum):
    """Two-byte message type, following the channel byte."""

    STATUS_UPDATE = b"\xaf\x13"
    CONFIGURATION = b"\xbf\x94"  # carries the MAC; not answered by every setup
    CONTROL_CONFIGURATION = b"\xbf\x24"  # model, software version
    CONTROL_CONFIGURATION_2 = b"\xbf\x2e"  # pumps, lights, blower, aux
    FILTER_CYCLES = b"\xbf\x23"
    ERROR = b"\xbf\xe1"
    READY = b"\xbf\x06"  # RS-485 send token, addressed to a specific channel
    NOTHING_TO_SEND = b"\xbf\x07"
    NEW_CLIENT_CLEAR_TO_SEND = b"\xbf\x00"

    CONFIGURATION_REQUEST = b"\xbf\x04"
    CONTROL_CONFIGURATION_REQUEST = b"\xbf\x22"
    TOGGLE_ITEM = b"\xbf\x11"
    SET_TEMPERATURE = b"\xbf\x20"
    SET_TIME = b"\xbf\x21"
    SET_TEMPERATURE_SCALE = b"\xbf\x27"


#: Payloads of the three control configuration requests.
CONTROL_CONFIG_REQUEST_PAYLOADS: dict[int, bytes] = {
    1: b"\x02\x00\x00",  # -> CONTROL_CONFIGURATION
    2: b"\x00\x00\x01",  # -> CONTROL_CONFIGURATION_2
    3: b"\x01\x00\x00",  # -> FILTER_CYCLES
}


class ToggleItem(IntEnum):
    """Items that can be cycled with a TOGGLE_ITEM message."""

    NORMAL_OPERATION = 0x01
    CLEAR_NOTIFICATION = 0x03
    PUMP_1 = 0x04
    PUMP_2 = 0x05
    PUMP_3 = 0x06
    PUMP_4 = 0x07
    PUMP_5 = 0x08
    PUMP_6 = 0x09
    BLOWER = 0x0C
    MISTER = 0x0E
    LIGHT_1 = 0x11
    LIGHT_2 = 0x12
    AUX_1 = 0x16
    AUX_2 = 0x17
    SOAK = 0x1D
    HOLD = 0x3C
    TEMPERATURE_RANGE = 0x50
    HEATING_MODE = 0x51

    @classmethod
    def pump(cls, index: int) -> ToggleItem:
        """Toggle code for pump `index` (0-based)."""
        if not 0 <= index < 6:
            raise ValueError(f"pump index out of range: {index}")
        return cls(cls.PUMP_1 + index)

    @classmethod
    def light(cls, index: int) -> ToggleItem:
        """Toggle code for light `index` (0-based)."""
        if not 0 <= index < 2:
            raise ValueError(f"light index out of range: {index}")
        return cls(cls.LIGHT_1 + index)

    @classmethod
    def aux(cls, index: int) -> ToggleItem:
        """Toggle code for auxiliary output `index` (0-based)."""
        if not 0 <= index < 2:
            raise ValueError(f"aux index out of range: {index}")
        return cls(cls.AUX_1 + index)


class HeatMode(IntEnum):
    """Heating mode as reported in the status update."""

    READY = 0x00
    REST = 0x01
    READY_IN_REST = 0x02


class TemperatureRange(IntEnum):
    LOW = 0
    HIGH = 1


class TemperatureUnit(StrEnum):
    CELSIUS = "celsius"
    FAHRENHEIT = "fahrenheit"


class Notification(IntEnum):
    """Reminder notifications the controller raises."""

    NONE = 0x00
    FILTER = 0x04
    SANITIZER = 0x09
    PH = 0x0A


#: Celsius is transmitted in half degrees; Fahrenheit in whole ones.
CELSIUS_DIVISOR = 2.0

#: Sentinel the controller sends while the water temperature is unknown
#: (typically right after power-up, before the pump has circulated).
TEMPERATURE_UNKNOWN = 0xFF

MAX_PUMPS = 6
MAX_LIGHTS = 2
MAX_AUX = 2
