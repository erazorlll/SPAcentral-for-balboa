"""Manual, one-time clock sync."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import SpaConfigEntry, sync_clock
from .entity import BalboaEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SpaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([BalboaSyncClockButton(entry)])


class BalboaSyncClockButton(BalboaEntity, ButtonEntity):
    """Push Home Assistant's current time to the spa right now.

    Independent of the `sync_time` option, which only controls the hourly
    background sync -- this is a distinct, user-initiated action.
    """

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, entry: SpaConfigEntry) -> None:
        super().__init__(entry, "sync_clock")

    async def async_press(self) -> None:
        await sync_clock(self._client)
