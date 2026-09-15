"""Binary sensors."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import SpaConfigEntry
from .balboa import SpaState
from .const import DOMAIN, OPT_HAS_CIRCULATION_PUMP
from .entity import BalboaEntity
from .identity import entity_unique_id


def _has_circulation_pump(entry: SpaConfigEntry) -> bool:
    """Whether to offer the circulation pump sensor at all.

    The controller's own hardware descriptor answers this reliably. Without
    one, the manual fallback's answer counts -- except for entries set up
    before that question was asked, which keep the sensor they always had:
    its value comes straight from the status broadcast, and those controllers
    (observed: SIBP2P/Colossus boards) do send that.
    """
    state = entry.runtime_data.state
    if state.hardware_reported or OPT_HAS_CIRCULATION_PUMP in entry.options:
        return state.has_circulation_pump
    return True


@dataclass(frozen=True, kw_only=True)
class BalboaBinarySensorDescription(BinarySensorEntityDescription):
    """A binary sensor, how to read it, and whether this spa has it."""

    value: Callable[[SpaState], bool]
    exists: Callable[[SpaConfigEntry], bool] = lambda _entry: True


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
        exists=_has_circulation_pump,
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
    """Create only what this spa reports having.

    A sensor this spa turns out not to have is also dropped from the entity
    registry, so an entry created before that was known does not keep a
    permanently unavailable leftover.
    """
    registry = er.async_get(hass)
    entities = []
    for description in BINARY_SENSORS:
        if description.exists(entry):
            entities.append(BalboaBinarySensor(entry, description))
        elif entity_id := registry.async_get_entity_id(
            Platform.BINARY_SENSOR, DOMAIN, entity_unique_id(entry, description.key)
        ):
            registry.async_remove(entity_id)
    async_add_entities(entities)


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
