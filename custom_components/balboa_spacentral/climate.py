"""The spa itself, as a thermostat."""

from __future__ import annotations

from typing import Any, ClassVar

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import SpaConfigEntry
from .balboa import HeatMode, TemperatureRange, TemperatureUnit
from .entity import BalboaEntity

#: The controller accepts these ranges; taken from the long-standing Ruby
#: implementation rather than guessed, and independent of the selected range.
LIMITS: dict[TemperatureUnit, tuple[float, float]] = {
    TemperatureUnit.CELSIUS: (10.0, 40.0),
    TemperatureUnit.FAHRENHEIT: (50.0, 106.0),
}

#: Rest is the spa's way of being off: it only heats during a filter cycle.
#: Ready-in-rest is a state the controller enters by itself and cannot be
#: selected, so it is reported but never offered.
HEAT_MODE_TO_HVAC: dict[HeatMode, HVACMode] = {
    HeatMode.READY: HVACMode.HEAT,
    HeatMode.REST: HVACMode.OFF,
    HeatMode.READY_IN_REST: HVACMode.AUTO,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SpaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([BalboaClimate(entry)])


class BalboaClimate(BalboaEntity, ClimateEntity):
    """Water temperature, heating mode and temperature range in one card."""

    _attr_name = None  # the device name alone reads better here
    _attr_hvac_modes: ClassVar[list[HVACMode]] = [HVACMode.HEAT, HVACMode.OFF]
    _attr_preset_modes: ClassVar[list[str]] = [
        item.name.lower() for item in TemperatureRange
    ]
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.PRESET_MODE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )
    _enable_turn_on_off_backwards_compatibility = False

    def __init__(self, entry: SpaConfigEntry) -> None:
        super().__init__(entry, "spa")

    @property
    def temperature_unit(self) -> str:
        """Follow the controller, which can be switched between °C and °F."""
        if self._client.temperature_unit is TemperatureUnit.FAHRENHEIT:
            return UnitOfTemperature.FAHRENHEIT
        return UnitOfTemperature.CELSIUS

    @property
    def target_temperature_step(self) -> float:
        return self._client.temperature_step

    @property
    def min_temp(self) -> float:
        return LIMITS[self._client.temperature_unit][0]

    @property
    def max_temp(self) -> float:
        return LIMITS[self._client.temperature_unit][1]

    @property
    def current_temperature(self) -> float | None:
        """None while the controller has not measured yet, e.g. after power-up."""
        return self.spa.status.current_temperature if self.spa.status else None

    @property
    def target_temperature(self) -> float | None:
        return self.spa.status.target_temperature if self.spa.status else None

    @property
    def hvac_mode(self) -> HVACMode | None:
        if self.spa.status is None:
            return None
        return HEAT_MODE_TO_HVAC.get(self.spa.status.heat_mode)

    @property
    def hvac_action(self) -> HVACAction | None:
        if self.spa.status is None:
            return None
        return HVACAction.HEATING if self.spa.status.heating else HVACAction.IDLE

    @property
    def preset_mode(self) -> str | None:
        if self.spa.status is None:
            return None
        return self.spa.status.temperature_range.name.lower()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        if (temperature := kwargs.get(ATTR_TEMPERATURE)) is not None:
            await self._client.set_target_temperature(float(temperature))

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        mode = HeatMode.READY if hvac_mode is HVACMode.HEAT else HeatMode.REST
        await self._client.set_heat_mode(mode)

    async def async_turn_on(self) -> None:
        await self.async_set_hvac_mode(HVACMode.HEAT)

    async def async_turn_off(self) -> None:
        await self.async_set_hvac_mode(HVACMode.OFF)

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        await self._client.set_temperature_range(TemperatureRange[preset_mode.upper()])
