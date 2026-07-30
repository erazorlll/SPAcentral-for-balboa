"""Pumps and the blower.

All of them are fans, whether they have one speed or two. A spa where pump 1 is
a switch and pump 2 a fan would make every automation and dashboard depend on
which hardware happens to be fitted.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import SpaConfigEntry
from .balboa import MAX_PUMPS
from .entity import BalboaEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SpaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """One entity per pump the spa reports, plus the blower if fitted."""
    state = entry.runtime_data.state
    entities: list[BalboaEntity] = [
        BalboaPump(entry, index) for index in range(MAX_PUMPS) if state.pump_speeds(index)
    ]
    if state.blower_speeds:
        entities.append(BalboaBlower(entry))
    async_add_entities(entities)


class _BalboaFan(BalboaEntity, FanEntity):
    """Shared percentage handling for anything with one or two speeds."""

    _attr_supported_features = (
        FanEntityFeature.SET_SPEED | FanEntityFeature.TURN_ON | FanEntityFeature.TURN_OFF
    )
    _enable_turn_on_off_backwards_compatibility = False

    @property
    def _speeds(self) -> int:
        raise NotImplementedError

    @property
    def _current(self) -> int:
        raise NotImplementedError

    async def _drive(self, speed: int) -> None:
        raise NotImplementedError

    @property
    def speed_count(self) -> int:
        return max(self._speeds, 1)

    @property
    def is_on(self) -> bool:
        return self._current != 0

    @property
    def percentage(self) -> int:
        """Percentage of the available speeds.

        A single-speed pump reports 2 when running rather than 1, so anything
        non-zero simply means full.
        """
        if not self._current:
            return 0
        if self._speeds <= 1:
            return 100
        return min(int(self._current / self._speeds * 100), 100)

    async def async_set_percentage(self, percentage: int) -> None:
        if percentage == 0:
            await self._drive(0)
            return
        if self._speeds <= 1:
            await self._drive(1)
            return
        speed = max(1, min(self._speeds, round(percentage / 100 * self._speeds)))
        await self._drive(speed)

    async def async_turn_on(
        self,
        percentage: int | None = None,
        preset_mode: str | None = None,
        **kwargs: Any,
    ) -> None:
        await self.async_set_percentage(percentage if percentage is not None else 100)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._drive(0)


class BalboaPump(_BalboaFan):
    """One jet pump."""

    def __init__(self, entry: SpaConfigEntry, index: int) -> None:
        super().__init__(entry, f"pump_{index + 1}")
        self._index = index

    @property
    def _speeds(self) -> int:
        return self.spa.pump_speeds(self._index)

    @property
    def _current(self) -> int:
        return self.spa.pump_state(self._index)

    async def _drive(self, speed: int) -> None:
        await self._client.set_pump(self._index, speed)


class BalboaBlower(_BalboaFan):
    """The air blower."""

    def __init__(self, entry: SpaConfigEntry) -> None:
        super().__init__(entry, "blower")

    @property
    def _speeds(self) -> int:
        return self.spa.blower_speeds

    @property
    def _current(self) -> int:
        return self.spa.status.blower if self.spa.status else 0

    async def _drive(self, speed: int) -> None:
        await self._client.set_blower(speed)
