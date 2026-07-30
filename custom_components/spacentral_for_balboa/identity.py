"""Device identity.

The one place where this integration differs decisively from every other
Balboa client, and the reason it works at all on an RS-485 gateway.

Entity identity must be unique, stable across restarts and IP changes,
independent of the display name, and available in *every* setup. A MAC address
fails the last of those: the two spas this was developed against are the same
model, on the same firmware, and neither answers the request that carries one.
Deriving identity from the device would make them collide.

So: the MAC when it exists, and Home Assistant's own `entry_id` otherwise --
a UUID that is unique by construction and outlives everything the user can
change.
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_MAC
from homeassistant.helpers.device_registry import format_mac

from .const import CONF_IDENTITY_SOURCE, IDENTITY_ENTRY_ID, IDENTITY_MAC

__all__ = ["device_key", "entity_unique_id", "initial_identity_source"]


def initial_identity_source(mac: str | None) -> str:
    """Decide, once, where this entry's identity comes from."""
    return IDENTITY_MAC if mac else IDENTITY_ENTRY_ID


def device_key(entry: ConfigEntry) -> str:
    """Stable key behind the device and every entity of this entry.

    Reads the source recorded at setup rather than re-deciding: a controller
    that starts reporting a MAC later must not silently re-identify the device
    and orphan every entity built from the old key.
    """
    source = entry.data.get(CONF_IDENTITY_SOURCE, IDENTITY_ENTRY_ID)
    if source == IDENTITY_MAC and (mac := entry.data.get(CONF_MAC)):
        return format_mac(mac).replace(":", "")
    return entry.entry_id


def entity_unique_id(entry: ConfigEntry, key: str) -> str:
    """Unique id for one entity of this spa."""
    return f"{device_key(entry)}_{key}"
