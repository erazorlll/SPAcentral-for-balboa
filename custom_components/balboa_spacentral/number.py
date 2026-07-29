"""How long the filter cycles run."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import SpaConfigEntry
from .entity import BalboaEntity

#: The controller stores a duration as whole hours plus minutes, so a quarter
#: hour is the smallest step that stays exactly representable.
STEP_MINUTES = 15
MAX_MINUTES = 24 * 60


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
    async_add_entities(BalboaFilterCycleDuration(entry, cycle) for cycle in (1, 2))


class BalboaFilterCycleDuration(BalboaEntity, NumberEntity):
    """Length of one filter cycle, in minutes."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_native_min_value = 0
    _attr_native_max_value = MAX_MINUTES
    _attr_native_step = STEP_MINUTES
    _attr_mode = NumberMode.BOX

    def __init__(self, entry: SpaConfigEntry, cycle: int) -> None:
        super().__init__(entry, f"filter_cycle_{cycle}_duration")
        self._cycle = cycle

    @property
    def native_value(self) -> float | None:
        cycles = self.spa.filter_cycles
        if cycles is None:
            return None
        return float(cycles.duration(self._cycle))

    async def async_set_native_value(self, value: float) -> None:
        cycles = self.spa.filter_cycles
        if cycles is None:
            return
        minutes = max(0, min(MAX_MINUTES, int(value)))
        await self._client.set_filter_cycles(cycles.with_duration(self._cycle, minutes))
