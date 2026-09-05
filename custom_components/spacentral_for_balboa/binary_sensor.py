"""Binary sensors."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import SpaConfigEntry
from .balboa import SpaState
from .entity import BalboaEntity


@dataclass(frozen=True, kw_only=True)
class BalboaBinarySensorDescription(BinarySensorEntityDescription):
    """A binary sensor, how to read it, and whether this spa has it."""

    value: Callable[[SpaState], bool]
    exists: Callable[[SpaState], bool] = lambda _state: True


BINARY_SENSORS: tuple[BalboaBinarySensorDescription, ...] = (
    BalboaBinarySensorDescription(
        key="heating",
        # POWER, not HEAT: HEAT is Home Assistant's "abnormal heat detected"
        # alarm class (states "Normal"/"Hot"), meant for a safety sensor, not
        # for "the heater element is currently on".
        device_class=BinarySensorDeviceClass.POWER,
        value=lambda state: bool(state.status and state.status.heating),
    ),
    BalboaBinarySensorDescription(
        key="circulation_pump",
        device_class=BinarySensorDeviceClass.RUNNING,
        # No `exists` gate: unlike a numbered pump/light, there is only ever
        # one of these, so a spa without one just shows a permanently-off
        # sensor -- a low-cost false positive next to never creating it at
        # all. That matters because `hardware.circulation_pump` never arrives
        # on some controllers (observed: SIBP2P/Colossus boards do not answer
        # the descriptor request at all), which used to hide this sensor
        # forever even though its value is read straight from the status
        # broadcast those boards do send.
        value=lambda state: bool(state.status and state.status.circulation_pump),
    ),
    BalboaBinarySensorDescription(
        key="filter_cycle_1",
        device_class=BinarySensorDeviceClass.RUNNING,
        value=lambda state: bool(state.status and state.status.filter_cycle_running[0]),
    ),
    BalboaBinarySensorDescription(
        key="filter_cycle_2",
        device_class=BinarySensorDeviceClass.RUNNING,
        value=lambda state: bool(state.status and state.status.filter_cycle_running[1]),
    ),
    BalboaBinarySensorDescription(
        key="priming",
        entity_category=EntityCategory.DIAGNOSTIC,
        value=lambda state: bool(state.status and state.status.priming),
    ),
    BalboaBinarySensorDescription(
        key="hold",
        entity_category=EntityCategory.DIAGNOSTIC,
        value=lambda state: bool(state.status and state.status.hold),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SpaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create only what this spa reports having."""
    state = entry.runtime_data.state
    async_add_entities(
        BalboaBinarySensor(entry, description)
        for description in BINARY_SENSORS
        if description.exists(state)
    )


class BalboaBinarySensor(BalboaEntity, BinarySensorEntity):
    """One flag out of the status frame."""

    entity_description: BalboaBinarySensorDescription

    def __init__(
        self, entry: SpaConfigEntry, description: BalboaBinarySensorDescription
    ) -> None:
        super().__init__(entry, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool:
        return self.entity_description.value(self.spa)
