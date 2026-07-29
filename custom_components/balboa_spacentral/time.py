"""When the filter cycles start."""

from __future__ import annotations

from datetime import time as dt_time

from homeassistant.components.time import TimeEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import SpaConfigEntry
from .entity import BalboaEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SpaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Always created.

    Waiting for the filter cycle frame would make the entities depend on a
    message that can be lost to a bus collision -- and unlike the configuration
    gap-filler, platform setup runs only once, so they would never appear at
    all. They report unknown until the frame arrives instead.
    """
    async_add_entities(BalboaFilterCycleStart(entry, cycle) for cycle in (1, 2))


class BalboaFilterCycleStart(BalboaEntity, TimeEntity):
    """Start time of one filter cycle."""

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, entry: SpaConfigEntry, cycle: int) -> None:
        super().__init__(entry, f"filter_cycle_{cycle}_start")
        self._cycle = cycle

    @property
    def native_value(self) -> dt_time | None:
        cycles = self.spa.filter_cycles
        if cycles is None:
            return None
        return dt_time(*cycles.start(self._cycle))

    async def async_set_value(self, value: dt_time) -> None:
        cycles = self.spa.filter_cycles
        if cycles is None:
            return
        await self._client.set_filter_cycles(
            cycles.with_start(self._cycle, value.hour, value.minute)
        )
