"""Spa lighting."""

from __future__ import annotations

from typing import Any, ClassVar

from homeassistant.components.light import ColorMode, LightEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import SpaConfigEntry
from .balboa import MAX_LIGHTS
from .entity import BalboaEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SpaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    state = entry.runtime_data.state
    async_add_entities(
        BalboaLight(entry, index) for index in range(MAX_LIGHTS) if state.has_light(index)
    )


class BalboaLight(BalboaEntity, LightEntity):
    """A light circuit. The protocol offers on and off, nothing else."""

    _attr_color_mode = ColorMode.ONOFF
    _attr_supported_color_modes: ClassVar[set[ColorMode]] = {ColorMode.ONOFF}

    def __init__(self, entry: SpaConfigEntry, index: int) -> None:
        super().__init__(entry, f"light_{index + 1}")
        self._index = index

    @property
    def is_on(self) -> bool:
        return self.spa.is_light_on(self._index)

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._client.set_light(self._index, True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._client.set_light(self._index, False)
