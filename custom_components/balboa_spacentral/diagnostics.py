"""Diagnostics download.

Aimed at making a bug report answerable without a round of questions: what the
spa says it is, what the link looks like, and how clean the byte stream is.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_HOST, CONF_MAC
from homeassistant.core import HomeAssistant

from . import SpaConfigEntry
from .const import CONF_DEVICE_PATH
from .identity import device_key

#: The address says where someone's spa lives and the MAC identifies the
#: hardware; neither is needed to diagnose a protocol problem.
TO_REDACT = {CONF_HOST, CONF_MAC, CONF_DEVICE_PATH}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: SpaConfigEntry
) -> dict[str, Any]:
    """Everything useful for a bug report, with the addresses removed."""
    client = entry.runtime_data
    state = client.state

    status = asdict(state.status) if state.status else None
    if status is not None:
        status.pop("raw", None)

    hardware = asdict(state.hardware) if state.hardware else None
    if hardware is not None:
        hardware.pop("raw", None)

    cycles = asdict(state.filter_cycles) if state.filter_cycles else None
    if cycles is not None:
        cycles.pop("raw", None)

    return {
        "entry": {
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": dict(entry.options),
            "identity_key_is_entry_id": device_key(entry) == entry.entry_id,
        },
        "connection": {
            "available": client.available,
            "connected": client.connected,
            "frames_read": client.frames_read,
            "crc_errors": client.crc_errors,
            "unknown_messages": client.unknown_messages,
        },
        "spa": {
            "model": state.model,
            "software_version": state.software_version,
            "has_mac": state.mac_address is not None,
            "hardware": hardware,
            "filter_cycles": cycles,
            "status": status,
        },
    }
