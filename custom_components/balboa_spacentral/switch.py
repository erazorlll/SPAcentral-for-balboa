"""Auxiliary outputs and the mister.

Pumps and the blower are fans, not switches -- see fan.py.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import SpaConfigEntry
from .balboa import MAX_AUX, ToggleItem
from .entity import BalboaEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SpaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    state = entry.runtime_data.state
    entities: list[BalboaEntity] = [
        BalboaAux(entry, index) for index in range(MAX_AUX) if state.has_aux(index)
    ]
    if state.has_mister:
        entities.append(BalboaMister(entry))
    if state.filter_cycles is not None:
        entities.append(BalboaFilterCycle2(entry))
    async_add_entities(entities)


class BalboaAux(BalboaEntity, SwitchEntity):
    """An auxiliary output."""

    def __init__(self, entry: SpaConfigEntry, index: int) -> None:
        super().__init__(entry, f"aux_{index + 1}")
        self._index = index

    @property
    def is_on(self) -> bool:
        return self.spa.is_aux_on(self._index)

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._client.set_aux(self._index, True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._client.set_aux(self._index, False)


class BalboaMister(BalboaEntity, SwitchEntity):
    """The mister."""

    def __init__(self, entry: SpaConfigEntry) -> None:
        super().__init__(entry, "mister")

    @property
    def is_on(self) -> bool:
        return bool(self.spa.status and self.spa.status.mister)

    async def async_turn_on(self, **kwargs: Any) -> None:
        if not self.is_on:
            await self._client.toggle_item(ToggleItem.MISTER)

    async def async_turn_off(self, **kwargs: Any) -> None:
        if self.is_on:
            await self._client.toggle_item(ToggleItem.MISTER)


class BalboaFilterCycle2(BalboaEntity, SwitchEntity):
    """Whether the second filter cycle runs at all.

    Stored in the high bit of that cycle's start hour, so switching it means
    writing the whole filter cycle block back.
    """

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, entry: SpaConfigEntry) -> None:
        super().__init__(entry, "filter_cycle_2_enabled")

    @property
    def is_on(self) -> bool:
        cycles = self.spa.filter_cycles
        return bool(cycles and cycles.cycle_2_enabled)

    async def _set(self, enabled: bool) -> None:
        cycles = self.spa.filter_cycles
        if cycles is None or cycles.cycle_2_enabled == enabled:
            return
        await self._client.set_filter_cycles(replace(cycles, cycle_2_enabled=enabled))

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._set(False)
