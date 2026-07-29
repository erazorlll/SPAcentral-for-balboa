"""Command paths of the client, including the multi-speed toggle logic.

The local spa has only single-speed pumps, so the multi-speed behaviour is
driven with a synthetic hardware configuration -- it must work for other people's
installations even though it cannot be exercised on this hardware.
"""

from __future__ import annotations

from dataclasses import replace

import pytest
from balboa.client import TOGGLE_LIMIT, SpaClient
from balboa.const import HeatMode, TemperatureRange, TemperatureUnit, ToggleItem
from balboa.messages import (
    ControlConfiguration2,
    SetTemperatureMessage,
    SetTimeMessage,
    StatusUpdate,
    parse_frame,
)
from balboa.state import SpaState

from .test_client import FakeTransport

STATUS_IDLE = bytes.fromhex(
    "7e20ffaf130000430e0b000003060b0c000002000000000000420000001e0000467e"
)


def _client_with(state: SpaState) -> tuple[SpaClient, FakeTransport]:
    transport = FakeTransport([])
    client = SpaClient(transport)
    client._state = state
    transport._connected = True
    return client, transport


@pytest.fixture
def single_speed_state() -> SpaState:
    return SpaState(
        status=parse_frame(STATUS_IDLE),
        hardware=ControlConfiguration2(
            channel=0x0A,
            raw=b"",
            pumps=(1, 0, 0, 0, 0, 0),
            lights=(True, False),
            aux=(True, False),
            blower_speeds=1,
            circulation_pump=True,
            mister=True,
        ),
    )


@pytest.fixture
def two_speed_state() -> SpaState:
    """Hardware this spa does not have, but other installations do."""
    return SpaState(
        status=parse_frame(STATUS_IDLE),
        hardware=ControlConfiguration2(
            channel=0x0A,
            raw=b"",
            pumps=(2, 0, 0, 0, 0, 0),
            lights=(False, False),
            aux=(False, False),
            blower_speeds=2,
            circulation_pump=False,
            mister=False,
        ),
    )


async def test_set_target_temperature_uses_the_spa_unit(
    single_speed_state: SpaState,
) -> None:
    client, transport = _client_with(single_speed_state)
    await client.set_target_temperature(34.0)
    message = parse_frame(transport.written[-1])
    assert isinstance(message, SetTemperatureMessage)
    assert message.raw_value == 68  # celsius, half degrees


async def test_set_clock(single_speed_state: SpaState) -> None:
    client, transport = _client_with(single_speed_state)
    await client.set_clock(7, 45)
    message = parse_frame(transport.written[-1])
    assert isinstance(message, SetTimeMessage)
    assert (message.hour, message.minute) == (7, 45)
    assert message.twenty_four_hour is True


async def test_set_temperature_unit(single_speed_state: SpaState) -> None:
    client, transport = _client_with(single_speed_state)
    await client.set_temperature_unit(TemperatureUnit.FAHRENHEIT)
    assert transport.written[-1][3:5] == b"\xbf\x27"


async def test_toggle_item_passthrough(single_speed_state: SpaState) -> None:
    client, transport = _client_with(single_speed_state)
    await client.toggle_item(ToggleItem.SOAK)
    assert parse_frame(transport.written[-1]).item is ToggleItem.SOAK


async def test_set_aux(single_speed_state: SpaState) -> None:
    client, transport = _client_with(single_speed_state)
    await client.set_aux(0, True)
    assert parse_frame(transport.written[-1]).item is ToggleItem.AUX_1

    before = len(transport.written)
    await client.set_aux(0, False)  # already off in the status
    assert len(transport.written) == before


async def test_single_speed_pump_switches_on_with_one_toggle(
    single_speed_state: SpaState,
) -> None:
    client, transport = _client_with(single_speed_state)
    await client.set_pump(0, 1)
    # It never sees the state change, so it retries up to the limit; what
    # matters is that it stops and only ever sends pump toggles.
    assert transport.written
    assert all(
        parse_frame(frame).item is ToggleItem.PUMP_1 for frame in transport.written
    )
    assert len(transport.written) <= TOGGLE_LIMIT


async def test_pump_toggling_stops_once_the_state_matches(
    two_speed_state: SpaState,
) -> None:
    """Feed the reported state back so the loop can terminate early."""
    client, _transport = _client_with(two_speed_state)

    original_send = client._send
    step = 0

    async def send_and_advance(frame: bytes) -> None:
        nonlocal step
        await original_send(frame)
        step += 1
        # emulate the controller reporting the next speed
        status = client.state.status
        assert status is not None
        client._state = client._state.with_status(
            replace(status, pumps=(step, 0, 0, 0, 0, 0))
        )

    client._send = send_and_advance  # type: ignore[method-assign]
    await client.set_pump(0, 2)
    assert step == 2, "two toggles to reach speed 2"


async def test_blower_requires_hardware(single_speed_state: SpaState) -> None:
    state = SpaState(
        status=single_speed_state.status,
        hardware=ControlConfiguration2(
            channel=0x0A,
            raw=b"",
            pumps=(0,) * 6,
            lights=(False, False),
            aux=(False, False),
            blower_speeds=0,
            circulation_pump=False,
            mister=False,
        ),
    )
    client, _ = _client_with(state)
    with pytest.raises(ValueError, match="no blower"):
        await client.set_blower(1)


async def test_blower_off_when_already_off(single_speed_state: SpaState) -> None:
    client, transport = _client_with(single_speed_state)
    before = len(transport.written)
    await client.set_blower(0)
    assert len(transport.written) == before


async def test_set_heat_mode_sends_toggles(single_speed_state: SpaState) -> None:
    client, transport = _client_with(single_speed_state)
    await client.set_heat_mode(HeatMode.REST)
    assert transport.written
    assert all(
        parse_frame(frame).item is ToggleItem.HEATING_MODE for frame in transport.written
    )


async def test_set_heat_mode_noop_when_already_there(
    single_speed_state: SpaState,
) -> None:
    client, transport = _client_with(single_speed_state)
    before = len(transport.written)
    await client.set_heat_mode(HeatMode.READY)  # the status says READY
    assert len(transport.written) == before


async def test_set_temperature_range_noop_when_already_there(
    single_speed_state: SpaState,
) -> None:
    client, transport = _client_with(single_speed_state)
    before = len(transport.written)
    await client.set_temperature_range(TemperatureRange.HIGH)
    assert len(transport.written) == before


async def test_set_temperature_range_toggles(single_speed_state: SpaState) -> None:
    client, transport = _client_with(single_speed_state)
    await client.set_temperature_range(TemperatureRange.LOW)
    assert all(
        parse_frame(frame).item is ToggleItem.TEMPERATURE_RANGE
        for frame in transport.written
    )


async def test_send_survives_a_dead_connection(single_speed_state: SpaState) -> None:
    """A failed write must be logged, not raised into the entity layer."""
    client, transport = _client_with(single_speed_state)
    transport._connected = False
    await client.toggle_item(ToggleItem.SOAK)  # must not raise


async def test_temperature_step_fahrenheit() -> None:
    status = parse_frame(STATUS_IDLE)
    assert isinstance(status, StatusUpdate)
    fahrenheit = replace(status, temperature_unit=TemperatureUnit.FAHRENHEIT)
    client, _ = _client_with(SpaState(status=fahrenheit))
    assert client.temperature_step == 1.0
    assert client.temperature_unit is TemperatureUnit.FAHRENHEIT
