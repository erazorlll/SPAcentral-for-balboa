"""Balboa spa protocol library.

Deliberately free of any Home Assistant import: it is testable against recorded
byte streams on its own and could be published separately unchanged.
"""

from .client import SpaClient
from .const import (
    FAULT_CODES,
    MAX_AUX,
    MAX_LIGHTS,
    MAX_PUMPS,
    HeatMode,
    MessageType,
    Notification,
    TemperatureRange,
    TemperatureUnit,
    ToggleItem,
)
from .discovery import BALBOA_OUI, DiscoveredSpa, async_discover
from .framing import FrameReader, build_frame, checksum
from .messages import (
    ControlConfiguration,
    ControlConfiguration2,
    FaultLogEntry,
    FilterCycles,
    Message,
    ModuleConfiguration,
    StatusUpdate,
    UnknownMessage,
    parse_frame,
)
from .state import SpaState
from .transport import (
    GATEWAY_PORT,
    WIFI_MODULE_PORT,
    SerialTransport,
    TcpTransport,
    Transport,
)

__all__ = [
    "BALBOA_OUI",
    "FAULT_CODES",
    "GATEWAY_PORT",
    "MAX_AUX",
    "MAX_LIGHTS",
    "MAX_PUMPS",
    "WIFI_MODULE_PORT",
    "ControlConfiguration",
    "ControlConfiguration2",
    "DiscoveredSpa",
    "FaultLogEntry",
    "FilterCycles",
    "FrameReader",
    "HeatMode",
    "Message",
    "MessageType",
    "ModuleConfiguration",
    "Notification",
    "SerialTransport",
    "SpaClient",
    "SpaState",
    "StatusUpdate",
    "TcpTransport",
    "TemperatureRange",
    "TemperatureUnit",
    "ToggleItem",
    "Transport",
    "UnknownMessage",
    "async_discover",
    "build_frame",
    "checksum",
    "parse_frame",
]
