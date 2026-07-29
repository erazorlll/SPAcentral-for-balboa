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
    """Only offered once the controller has told us its cycles."""
    if entry.runtime_data.state.filter_cycles is None:
        return
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
