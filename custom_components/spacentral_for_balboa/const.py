"""Constants of the Home Assistant layer."""

from __future__ import annotations

from typing import Final

from homeassistant.const import Platform

DOMAIN: Final = "spacentral_for_balboa"
MANUFACTURER: Final = "Balboa Water Group"

PLATFORMS: Final[list[Platform]] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.CLIMATE,
    Platform.EVENT,
    Platform.FAN,
    Platform.LIGHT,
    Platform.NUMBER,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.TIME,
]

# ── Configuration keys ────────────────────────────────────────────────────────
CONF_CONNECTION: Final = "connection"
CONF_DEVICE_PATH: Final = "device_path"
CONF_IDENTITY_SOURCE: Final = "identity_source"

CONNECTION_WIFI_MODULE: Final = "wifi_module"
CONNECTION_GATEWAY: Final = "gateway"
CONNECTION_SERIAL: Final = "serial"

#: How the device is identified. Frozen at first successful setup and never
#: changed afterwards.
IDENTITY_MAC: Final = "mac"
IDENTITY_ENTRY_ID: Final = "entry_id"

# ── Options ───────────────────────────────────────────────────────────────────
OPT_SYNC_TIME: Final = "sync_time"
DEFAULT_SYNC_TIME: Final = False

#: A manual fallback for what's fitted, used only while the controller itself
#: never answers the hardware descriptor request (observed: SIBP2P/Colossus
#: boards). Ignored entirely once real hardware is known -- see
#: `SpaClient.apply_manual_hardware`.
OPT_PUMP_COUNT: Final = "pump_count"
OPT_LIGHT_COUNT: Final = "light_count"
OPT_AUX_COUNT: Final = "aux_count"
OPT_HAS_BLOWER: Final = "has_blower"
OPT_HAS_CIRCULATION_PUMP: Final = "has_circulation_pump"
OPT_HAS_MISTER: Final = "has_mister"
DEFAULT_PUMP_COUNT: Final = 0
DEFAULT_LIGHT_COUNT: Final = 0
DEFAULT_AUX_COUNT: Final = 0
DEFAULT_HAS_BLOWER: Final = False
DEFAULT_HAS_CIRCULATION_PUMP: Final = False
DEFAULT_HAS_MISTER: Final = False
