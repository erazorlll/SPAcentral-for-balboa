"""Reminders the controller raises.

Deliberately built on the notification field of the status frame rather than on
the fault log: the log needs a message type this project has never seen on real
hardware, and shipping a parser for a frame nobody has captured would be
guesswork. Reminders, on the other hand, arrive in every status frame.
"""

from __future__ import annotations

from homeassistant.components.event import EventEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import SpaConfigEntry
from .balboa import Notification
from .entity import BalboaEntity

EVENT_TYPES = [
    item.name.lower() for item in Notification if item is not Notification.NONE
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SpaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([BalboaReminder(entry)])


class BalboaReminder(BalboaEntity, EventEntity):
    """Fires when the spa starts asking for maintenance."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_event_types = EVENT_TYPES

    def __init__(self, entry: SpaConfigEntry) -> None:
        super().__init__(entry, "reminder")
        self._last = Notification.NONE

    @callback
    def _handle_update(self) -> None:
        """Only the transition is an event; a standing reminder is not."""
        status = self.spa.status
        current = status.notification if status else Notification.NONE
        if current is not self._last:
            self._last = current
            if current is not Notification.NONE:
                self._trigger_event(current.name.lower())
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        status = self.spa.status
        self._last = status.notification if status else Notification.NONE
        self.async_on_remove(self._client.subscribe(self._handle_update))
