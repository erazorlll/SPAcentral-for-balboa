"""Entities: which ones exist, what they show, what they send.

The spa is driven through a fake transport replaying real captured frames, so
the entities are built from the hardware description an actual controller sent.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import patch

import pytest
from homeassistant.components.climate import (
    ATTR_HVAC_ACTION,
    ATTR_PRESET_MODE,
    HVACAction,
    HVACMode,
)
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_TEMPERATURE,
    CONF_HOST,
    CONF_PORT,
    STATE_OFF,
    STATE_ON,
    Platform,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.balboa_spacentral.balboa.framing import FrameReader
from custom_components.balboa_spacentral.balboa.messages import (
    ControlConfiguration,
    ControlConfiguration2,
    StatusUpdate,
    parse_frame,
)
from custom_components.balboa_spacentral.balboa.transport import Transport
from custom_components.balboa_spacentral.const import (
    CONF_CONNECTION,
    CONF_IDENTITY_SOURCE,
    CONNECTION_GATEWAY,
    DOMAIN,
    IDENTITY_ENTRY_ID,
)

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


def _frames(name: str, kind: type, limit: int = 1) -> list[bytes]:
    raw = (FIXTURES / f"{name}.bin").read_bytes()
    out: list[bytes] = []
    for frame in FrameReader().feed(raw):
        if isinstance(parse_frame(frame), kind):
            out.append(frame)
            if len(out) >= limit:
                break
    return out


class ReplayTransport(Transport):
    """Serves captured frames, then waits."""

    def __init__(self, frames: list[bytes]) -> None:
        self.description = "replay"
        self._queue: asyncio.Queue[bytes] = asyncio.Queue()
        for frame in frames:
            self._queue.put_nowait(frame)
        self.written: list[bytes] = []
        self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected

    async def connect(self) -> None:
        self._connected = True

    async def read(self) -> bytes:
        return await self._queue.get()

    async def write(self, data: bytes) -> None:
        self.written.append(data)

    async def close(self) -> None:
        self._connected = False


@pytest.fixture
async def spa(hass: HomeAssistant):
    """A fully set up spa, built from real captured configuration frames."""
    frames = (
        _frames("ew11_probe", ControlConfiguration)
        + _frames("ew11_probe", ControlConfiguration2)
        + _frames("ew11_idle", StatusUpdate)
    )
    transport = ReplayTransport(frames)

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Whirlpool",
        data={
            CONF_CONNECTION: CONNECTION_GATEWAY,
            CONF_HOST: "192.168.0.56",
            CONF_PORT: 8899,
            CONF_IDENTITY_SOURCE: IDENTITY_ENTRY_ID,
        },
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.balboa_spacentral.build_transport", return_value=transport
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    yield entry, transport

    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_only_fitted_hardware_becomes_entities(hass: HomeAssistant, spa) -> None:
    """This spa has three pumps, one light, a blower -- and no mister or aux."""
    entry, _ = spa
    entities = er.async_get(hass).entities

    ids = {e.entity_id for e in entities.values() if e.config_entry_id == entry.entry_id}

    assert "climate.whirlpool" in ids
    assert "fan.whirlpool_pump_1" in ids
    assert "fan.whirlpool_pump_3" in ids
    assert "fan.whirlpool_blower" in ids
    assert "light.whirlpool_light_1" in ids

    # not fitted, so not invented
    assert "fan.whirlpool_pump_4" not in ids
    assert "light.whirlpool_light_2" not in ids
    assert not [i for i in ids if "mister" in i]
    assert not [i for i in ids if "aux" in i]


async def test_device_is_named_and_identified(hass: HomeAssistant, spa) -> None:
    entry, _ = spa
    device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, entry.entry_id)})
    assert device is not None
    assert device.name == "Whirlpool"
    assert device.model == "BP6013G3"
    assert device.manufacturer == "Balboa Water Group"


async def test_climate_reports_the_captured_state(hass: HomeAssistant, spa) -> None:
    state = hass.states.get("climate.whirlpool")
    assert state is not None
    assert state.state == HVACMode.HEAT  # the capture has heat mode READY
    assert state.attributes["current_temperature"] == 33.5
    assert state.attributes[ATTR_TEMPERATURE] == 33.0
    assert state.attributes[ATTR_HVAC_ACTION] == HVACAction.IDLE
    assert state.attributes[ATTR_PRESET_MODE] == "high"
    assert state.attributes["target_temp_step"] == 0.5


async def test_setting_the_temperature_sends_a_command(hass: HomeAssistant, spa) -> None:
    _, transport = spa
    before = len(transport.written)

    await hass.services.async_call(
        Platform.CLIMATE,
        "set_temperature",
        {ATTR_ENTITY_ID: "climate.whirlpool", ATTR_TEMPERATURE: 34.0},
        blocking=True,
    )
    assert len(transport.written) > before
    # 0x44 = 68 = 34.0 °C in half degrees
    assert transport.written[-1][3:6].hex() == "bf2044"


async def test_pump_is_off_and_can_be_switched_on(hass: HomeAssistant, spa) -> None:
    _, transport = spa
    assert hass.states.get("fan.whirlpool_pump_1").state == STATE_OFF

    before = len(transport.written)
    await hass.services.async_call(
        Platform.FAN,
        "turn_on",
        {ATTR_ENTITY_ID: "fan.whirlpool_pump_1"},
        blocking=True,
    )
    assert len(transport.written) > before
    assert transport.written[-1][3:6].hex() == "bf1104"  # toggle pump 1


async def test_single_speed_pump_has_one_speed(hass: HomeAssistant, spa) -> None:
    """Reported as 2 when running, but it is still a one-speed pump."""
    state = hass.states.get("fan.whirlpool_pump_1")
    assert state.attributes["percentage_step"] == 100


async def test_light_can_be_switched(hass: HomeAssistant, spa) -> None:
    _, transport = spa
    assert hass.states.get("light.whirlpool_light_1").state == STATE_OFF

    await hass.services.async_call(
        Platform.LIGHT,
        "turn_on",
        {ATTR_ENTITY_ID: "light.whirlpool_light_1"},
        blocking=True,
    )
    assert transport.written[-1][3:6].hex() == "bf1111"  # toggle light 1


async def test_binary_sensors_follow_the_capture(hass: HomeAssistant, spa) -> None:
    assert hass.states.get("binary_sensor.whirlpool_circulation_pump").state == STATE_ON
    assert hass.states.get("binary_sensor.whirlpool_heating").state == STATE_OFF


async def test_sensors_follow_the_capture(hass: HomeAssistant, spa) -> None:
    assert hass.states.get("sensor.whirlpool_water_temperature").state == "33.5"
    assert hass.states.get("sensor.whirlpool_heat_mode").state == "ready"
    assert hass.states.get("sensor.whirlpool_temperature_range").state == "high"


async def test_unload_leaves_nothing_behind(hass: HomeAssistant, spa) -> None:
    entry, _ = spa
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert (
        hass.states.get("climate.whirlpool") is None
        or hass.states.get("climate.whirlpool").state == "unavailable"
    )
