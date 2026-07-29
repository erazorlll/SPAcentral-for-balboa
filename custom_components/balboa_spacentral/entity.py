"""Shared base for every entity of this integration."""

from __future__ import annotations

from homeassistant.const import CONF_MAC
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.entity import Entity

from .balboa import SpaClient, SpaState
from .const import DOMAIN, MANUFACTURER
from .identity import device_key, entity_unique_id


class BalboaEntity(Entity):
    """Base entity: identity, device info, availability, push updates."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, entry, key: str) -> None:  # type: ignore[no-untyped-def]
        self._entry = entry
        self._client: SpaClient = entry.runtime_data
        self._attr_unique_id = entity_unique_id(entry, key)
        self._attr_translation_key = key

        connections = set()
        if mac := entry.data.get(CONF_MAC):
            connections.add((CONNECTION_NETWORK_MAC, mac))

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_key(entry))},
            connections=connections,
            manufacturer=MANUFACTURER,
            model=self.spa.model,
            name=entry.title,
            sw_version=self.spa.software_version,
        )

    @property
    def spa(self) -> SpaState:
        """Current snapshot. Never mutated by entities."""
        return self._client.state

    @property
    def available(self) -> bool:
        """False as soon as frames stop arriving, not just on a closed socket."""
        return self._client.available

    async def async_added_to_hass(self) -> None:
        """Subscribe to the push updates the controller sends every ~300 ms."""
        self.async_on_remove(self._client.subscribe(self.async_write_ha_state))
