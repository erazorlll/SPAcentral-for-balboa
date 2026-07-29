"""The Balboa SPAcentral integration."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_MAC, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

from .balboa import SerialTransport, SpaClient, TcpTransport, Transport
from .const import (
    CONF_CONNECTION,
    CONF_DEVICE_PATH,
    CONNECTION_SERIAL,
    DEFAULT_SYNC_TIME,
    OPT_SYNC_TIME,
    PLATFORMS,
)

_LOGGER = logging.getLogger(__name__)

type SpaConfigEntry = ConfigEntry[SpaClient]

SYNC_TIME_INTERVAL = timedelta(hours=1)


def build_transport(data: Mapping[str, Any]) -> Transport:
    """Create the transport described by a config entry."""
    if data.get(CONF_CONNECTION) == CONNECTION_SERIAL:
        return SerialTransport(data[CONF_DEVICE_PATH])
    return TcpTransport(data[CONF_HOST], data[CONF_PORT])


async def async_setup_entry(hass: HomeAssistant, entry: SpaConfigEntry) -> bool:
    """Set up one spa from a config entry."""
    client = SpaClient(build_transport(dict(entry.data)))

    if not await client.connect():
        await client.disconnect()
        raise ConfigEntryNotReady(f"no usable response from {client.description}")

    entry.runtime_data = client
    entry.async_on_unload(client.disconnect)

    # A controller may report its MAC only after the handshake. Record it for
    # diagnostics and the network link, but never let it change the identity of
    # an entry that is already running -- see identity.py.
    if client.state.mac_address and not entry.data.get(CONF_MAC):
        hass.config_entries.async_update_entry(
            entry, data={**entry.data, CONF_MAC: client.state.mac_address}
        )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _setup_time_sync(hass, entry)
    entry.async_on_unload(entry.add_update_listener(_options_updated))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: SpaConfigEntry) -> bool:
    """Tear one spa down."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _options_updated(hass: HomeAssistant, entry: SpaConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


def _setup_time_sync(hass: HomeAssistant, entry: SpaConfigEntry) -> None:
    """Keep the spa clock in step with Home Assistant, if asked to."""
    if not entry.options.get(OPT_SYNC_TIME, DEFAULT_SYNC_TIME):
        return

    client = entry.runtime_data

    async def sync(_now: datetime) -> None:
        now = dt_util.as_local(dt_util.utcnow())
        status = client.state.status
        if status is None:
            return
        if (status.hour, status.minute) != (now.hour, now.minute):
            _LOGGER.debug("%s: syncing clock", client.description)
            await client.set_clock(now.hour, now.minute)

    entry.async_on_unload(async_track_time_interval(hass, sync, SYNC_TIME_INTERVAL))
