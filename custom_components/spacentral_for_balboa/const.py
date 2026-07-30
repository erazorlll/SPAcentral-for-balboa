"""Constants of the Home Assistant layer."""

from __future__ import annotations

from typing import Final

from homeassistant.const import Platform

DOMAIN: Final = "spacentral_for_balboa"
MANUFACTURER: Final = "Balboa Water Group"

PLATFORMS: Final[list[Platform]] = [
    Platform.BINARY_SENSOR,
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
