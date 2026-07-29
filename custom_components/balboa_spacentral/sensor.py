"""Sensors."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import SpaConfigEntry
from .balboa import SpaState, TemperatureUnit
from .entity import BalboaEntity


@dataclass(frozen=True, kw_only=True)
class BalboaSensorDescription(SensorEntityDescription):
    """A sensor plus how to read it out of the state."""

    value: Callable[[SpaState], float | str | None]
    exists: Callable[[SpaState], bool] = lambda _state: True


def _temperature_unit(state: SpaState) -> str:
    if state.status and state.status.temperature_unit is TemperatureUnit.FAHRENHEIT:
        return UnitOfTemperature.FAHRENHEIT
    return UnitOfTemperature.CELSIUS


SENSORS: tuple[BalboaSensorDescription, ...] = (
    BalboaSensorDescription(
        key="water_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value=lambda state: state.status.current_temperature if state.status else None,
    ),
    BalboaSensorDescription(
        key="target_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        entity_registry_enabled_default=False,
        value=lambda state: state.status.target_temperature if state.status else None,
    ),
    BalboaSensorDescription(
        key="heat_mode",
        device_class=SensorDeviceClass.ENUM,
        options=["ready", "rest", "ready_in_rest"],
        value=lambda state: state.status.heat_mode.name.lower() if state.status else None,
    ),
    BalboaSensorDescription(
        key="temperature_range",
        device_class=SensorDeviceClass.ENUM,
        options=["low", "high"],
        value=lambda state: (
            state.status.temperature_range.name.lower() if state.status else None
        ),
    ),
    BalboaSensorDescription(
        key="notification",
        device_class=SensorDeviceClass.ENUM,
        options=["none", "filter", "sanitizer", "ph"],
        value=lambda state: (
            state.status.notification.name.lower() if state.status else None
        ),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SpaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create only the sensors this particular spa can actually feed."""
    state = entry.runtime_data.state
    async_add_entities(
        BalboaSensor(entry, description)
        for description in SENSORS
        if description.exists(state)
    )


class BalboaSensor(BalboaEntity, SensorEntity):
    """One value read out of the status frame."""

    entity_description: BalboaSensorDescription

    def __init__(
        self, entry: SpaConfigEntry, description: BalboaSensorDescription
    ) -> None:
        super().__init__(entry, description.key)
        self.entity_description = description

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Follow the controller: it can be switched between °C and °F."""
        if self.entity_description.device_class is SensorDeviceClass.TEMPERATURE:
            return _temperature_unit(self.spa)
        return None

    @property
    def native_value(self) -> float | str | None:
        return self.entity_description.value(self.spa)
