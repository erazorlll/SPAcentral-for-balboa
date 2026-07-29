"""Client behaviour: handshake, state assembly, commands, availability.

Driven by a fake transport that replays real captured frames, so no hardware and
no network are involved.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from balboa.client import STALE_AFTER, SpaClient
from balboa.const import HeatMode, TemperatureUnit, ToggleItem
from balboa.framing import FrameReader
from balboa.messages import (
    ControlConfiguration,
    ControlConfiguration2,
    StatusUpdate,
    parse_frame,
)
from balboa.transport import Transport

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


def _frames_of(
    name: str, types: tuple[type, ...], limit: int | None = None
) -> list[bytes]:
    """Pull frames of the given message types out of a capture."""
    raw = (FIXTURES / f"{name}.bin").read_bytes()
    out: list[bytes] = []
    for frame in FrameReader().feed(raw):
        if isinstance(parse_frame(frame), types):
            out.append(frame)
            if limit and len(out) >= limit:
                break
    return out


class FakeTransport(Transport):
    """Replays a fixed list of frames, then blocks until told otherwise."""

    def __init__(self, frames: list[bytes]) -> None:
        self.description = "fake"
        self._queue: asyncio.Queue[bytes] = asyncio.Queue()
        for frame in frames:
            self._queue.put_nowait(frame)
        self.written: list[bytes] = []
        self._connected = False
        self.connect_calls = 0
        self.fail_connect = False

    @property
    def connected(self) -> bool:
        return self._connected

    async def connect(self) -> None:
        self.connect_calls += 1
        if self.fail_connect:
            raise ConnectionError("refused")
        self._connected = True

    async def read(self) -> bytes:
        return await self._queue.get()

    async def write(self, data: bytes) -> None:
        if not self._connected:
            raise ConnectionError("not connected")
        self.written.append(data)

    async def close(self) -> None:
        self._connected = False

    def push(self, frame: bytes) -> None:
        self._queue.put_nowait(frame)


@pytest.fixture
def handshake_frames() -> list[bytes]:
    """The minimum a controller must send for the client to become usable."""
    return (
        _frames_of("ew11_probe", (ControlConfiguration,), 1)
        + _frames_of("ew11_probe", (ControlConfiguration2,), 1)
        + _frames_of("ew11_idle", (StatusUpdate,), 1)
    )


async def _connected_client(frames: list[bytes]) -> tuple[SpaClient, FakeTransport]:
    transport = FakeTransport(frames)
    client = SpaClient(transport)
    assert await client.connect()
    return client, transport


async def test_connect_completes_without_a_mac(handshake_frames: list[bytes]) -> None:
    """The whole point: no MAC arrives, and setup succeeds anyway."""
    client, _ = await _connected_client(handshake_frames)
    try:
        assert client.state.ready
        assert client.state.mac_address is None
        assert client.state.model == "BP6013G3"
    finally:
        await client.disconnect()


async def test_connect_requests_configuration(handshake_frames: list[bytes]) -> None:
    client, transport = await _connected_client(handshake_frames)
    try:
        sent = [frame.hex() for frame in transport.written]
        assert sent[:4] == [
            "7e050abf04777e",  # configuration (the MAC one, often unanswered)
            "7e080abf22020000897e",  # control configuration
            "7e080abf22000001587e",  # hardware description
            "7e080abf22010000347e",  # filter cycles
        ]
        # The fault log follows in the background rather than holding up the
        # handshake -- 24 requests would add five seconds to it.
        await asyncio.sleep(0.05)
        assert "7e080abf222000001c7e" in [f.hex() for f in transport.written]
    finally:
        await client.disconnect()


async def test_connect_fails_without_hardware_configuration() -> None:
    """A status alone is not enough -- we would not know what entities to make."""
    frames = _frames_of("ew11_idle", (StatusUpdate,), 1)
    transport = FakeTransport(frames)
    client = SpaClient(transport)
    from balboa import client as client_module

    original = client_module.CONFIGURATION_TIMEOUT
    client_module.CONFIGURATION_TIMEOUT = 0.3
    try:
        assert not await client.connect()
    finally:
        client_module.CONFIGURATION_TIMEOUT = original
        await client.disconnect()


async def test_connect_reports_transport_failure() -> None:
    transport = FakeTransport([])
    transport.fail_connect = True
    client = SpaClient(transport)
    assert not await client.connect()
    await client.disconnect()


async def test_hardware_is_decoded(handshake_frames: list[bytes]) -> None:
    client, _ = await _connected_client(handshake_frames)
    try:
        state = client.state
        assert state.pump_speeds(0) == 1
        assert state.pump_speeds(3) == 0  # not fitted
        assert state.has_light(0) is True
        assert state.has_light(1) is False
        assert state.has_circulation_pump is True
        assert state.has_mister is False
        assert state.blower_speeds == 1
    finally:
        await client.disconnect()


async def test_listeners_fire_on_real_change(handshake_frames: list[bytes]) -> None:
    client, transport = await _connected_client(handshake_frames)
    calls = 0

    def listener() -> None:
        nonlocal calls
        calls += 1

    client.subscribe(listener)
    try:
        pump_on = _frames_of("ew11_panel", (StatusUpdate,), 1)
        # find a frame where the pump is running
        raw = (FIXTURES / "ew11_panel.bin").read_bytes()
        for frame in FrameReader().feed(raw):
            message = parse_frame(frame)
            if isinstance(message, StatusUpdate) and message.pumps[0]:
                pump_on = [frame]
                break

        transport.push(pump_on[0])
        await asyncio.sleep(0.05)
        assert calls >= 1
        assert client.state.is_pump_on(0)
    finally:
        await client.disconnect()


async def test_clock_tick_alone_does_not_notify(handshake_frames: list[bytes]) -> None:
    """Otherwise every entity would be rewritten once a minute for nothing."""
    client, transport = await _connected_client(handshake_frames)
    calls = 0

    def listener() -> None:
        nonlocal calls
        calls += 1

    client.subscribe(listener)
    try:
        raw = (FIXTURES / "ew11_idle.bin").read_bytes()
        statuses = [
            frame
            for frame in FrameReader().feed(raw)
            if isinstance(parse_frame(frame), StatusUpdate)
        ]
        differing = [
            frame
            for frame in statuses
            if parse_frame(frame).minute != parse_frame(statuses[0]).minute
        ]
        assert differing, "capture should span a minute boundary"

        transport.push(differing[0])
        await asyncio.sleep(0.05)
        assert calls == 0
    finally:
        await client.disconnect()


async def test_unsubscribe(handshake_frames: list[bytes]) -> None:
    client, _ = await _connected_client(handshake_frames)
    try:
        unsubscribe = client.subscribe(lambda: None)
        unsubscribe()
        unsubscribe()  # must be safe twice
    finally:
        await client.disconnect()


async def test_broken_listener_does_not_stop_the_loop(
    handshake_frames: list[bytes],
) -> None:
    client, transport = await _connected_client(handshake_frames)
    survived = False

    def bad() -> None:
        raise RuntimeError("boom")

    def good() -> None:
        nonlocal survived
        survived = True

    client.subscribe(bad)
    client.subscribe(good)
    try:
        raw = (FIXTURES / "ew11_panel.bin").read_bytes()
        for frame in FrameReader().feed(raw):
            message = parse_frame(frame)
            if isinstance(message, StatusUpdate) and message.pumps[0]:
                transport.push(frame)
                break
        await asyncio.sleep(0.05)
        assert survived
    finally:
        await client.disconnect()


async def test_set_light_only_toggles_when_needed(
    handshake_frames: list[bytes],
) -> None:
    client, transport = await _connected_client(handshake_frames)
    try:
        before = len(transport.written)
        await client.set_light(0, False)  # already off
        assert len(transport.written) == before

        await client.set_light(0, True)
        assert len(transport.written) == before + 1
        assert parse_frame(transport.written[-1]).item is ToggleItem.LIGHT_1
    finally:
        await client.disconnect()


async def test_set_pump_rejects_missing_pump(handshake_frames: list[bytes]) -> None:
    client, _ = await _connected_client(handshake_frames)
    try:
        with pytest.raises(ValueError, match="not fitted"):
            await client.set_pump(3, 1)
        with pytest.raises(ValueError, match="out of range"):
            await client.set_pump(9, 1)
    finally:
        await client.disconnect()


async def test_set_pump_stops_when_target_reached(
    handshake_frames: list[bytes],
) -> None:
    """Asking for off while already off must not send anything."""
    client, transport = await _connected_client(handshake_frames)
    try:
        before = len(transport.written)
        await client.set_pump(0, 0)
        assert len(transport.written) == before
    finally:
        await client.disconnect()


async def test_set_heat_mode_rejects_transient_mode(
    handshake_frames: list[bytes],
) -> None:
    client, _ = await _connected_client(handshake_frames)
    try:
        with pytest.raises(ValueError, match="cannot be set"):
            await client.set_heat_mode(HeatMode.READY_IN_REST)
    finally:
        await client.disconnect()


async def test_temperature_helpers(handshake_frames: list[bytes]) -> None:
    client, _ = await _connected_client(handshake_frames)
    try:
        assert client.temperature_unit is TemperatureUnit.CELSIUS
        assert client.temperature_step == 0.5
    finally:
        await client.disconnect()


async def test_availability_follows_the_frame_clock(
    handshake_frames: list[bytes], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A silent but open connection must read as unavailable."""
    client, _ = await _connected_client(handshake_frames)
    try:
        assert client.available

        import balboa.client as client_module

        real_monotonic = client_module.time.monotonic
        monkeypatch.setattr(
            client_module.time,
            "monotonic",
            lambda: real_monotonic() + STALE_AFTER + 1,
        )
        assert not client.available
    finally:
        await client.disconnect()


async def test_disconnect_is_idempotent(handshake_frames: list[bytes]) -> None:
    client, _ = await _connected_client(handshake_frames)
    await client.disconnect()
    await client.disconnect()
    assert not client.connected
