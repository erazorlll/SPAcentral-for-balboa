"""Reconnect, stale detection and the defensive parts of the read loop.

These paths matter most in practice: a serial-to-network gateway that quietly
stops forwarding is the everyday failure, and it keeps the TCP socket open while
doing so.
"""

from __future__ import annotations

import asyncio

import pytest
from balboa import client as client_module
from balboa.client import SpaClient
from balboa.framing import FrameReader
from balboa.messages import (
    ControlConfiguration,
    ControlConfiguration2,
    FilterCycles,
    StatusUpdate,
    parse_frame,
)

from .test_client import FIXTURES, FakeTransport, _frames_of


@pytest.fixture(autouse=True)
def _quick_monitor(monkeypatch: pytest.MonkeyPatch) -> None:
    """Shrink the watchdog timings so the tests do not take half a minute.

    Only the magnitudes change; the logic under test is identical.
    """
    monkeypatch.setattr(client_module, "STALE_AFTER", 0.1)
    monkeypatch.setattr(client_module, "RECONNECT_AFTER", 0.2)
    monkeypatch.setattr(client_module, "MONITOR_INTERVAL", 0.05)
    monkeypatch.setattr(client_module, "INITIAL_BACKOFF", 0.02)


@pytest.fixture
def handshake_frames() -> list[bytes]:
    return (
        _frames_of("ew11_probe", (ControlConfiguration,), 1)
        + _frames_of("ew11_probe", (ControlConfiguration2,), 1)
        + _frames_of("ew11_idle", (StatusUpdate,), 1)
    )


async def test_silent_link_triggers_a_reconnect(handshake_frames: list[bytes]) -> None:
    """Socket open, no frames -- the client must rebuild the connection."""
    transport = FakeTransport(handshake_frames)
    client = SpaClient(transport)
    assert await client.connect()
    try:
        connects_before = transport.connect_calls
        # Let the watchdog notice the silence and act on it.
        await asyncio.sleep(0.4)
        assert transport.connect_calls > connects_before
    finally:
        await client.disconnect()


async def test_availability_flips_and_notifies(handshake_frames: list[bytes]) -> None:
    transport = FakeTransport(handshake_frames)
    client = SpaClient(transport)
    assert await client.connect()
    seen: list[bool] = []
    client.subscribe(lambda: seen.append(client.available))
    try:
        assert client.available
        await asyncio.sleep(0.4)
        assert not client.available
        assert seen, "the watchdog must tell listeners about the change"
    finally:
        await client.disconnect()


async def test_reconnect_retries_after_a_refused_attempt(
    handshake_frames: list[bytes],
) -> None:
    transport = FakeTransport(handshake_frames)
    client = SpaClient(transport)
    assert await client.connect()
    try:
        transport.fail_connect = True
        await asyncio.sleep(0.4)
        assert transport.connect_calls > 1  # kept trying
    finally:
        await client.disconnect()


async def test_peer_closing_leads_to_a_reconnect(
    handshake_frames: list[bytes],
) -> None:
    """An empty read means the peer went away; the watchdog must rebuild."""
    transport = FakeTransport(handshake_frames)
    client = SpaClient(transport)
    assert await client.connect()
    try:
        connects_before = transport.connect_calls
        transport.push(b"")
        await asyncio.sleep(0.4)
        assert transport.connect_calls > connects_before
    finally:
        await client.disconnect()


async def test_garbage_does_not_break_the_client(
    handshake_frames: list[bytes],
) -> None:
    """Random bytes on the line must be counted and discarded, nothing more."""
    transport = FakeTransport(handshake_frames)
    client = SpaClient(transport)
    assert await client.connect()
    try:
        transport.push(bytes(range(256)))
        await asyncio.sleep(0.1)
        assert client.state.ready  # still usable
    finally:
        await client.disconnect()


async def test_unknown_messages_are_counted(handshake_frames: list[bytes]) -> None:
    from balboa.framing import build_frame

    transport = FakeTransport(handshake_frames)
    client = SpaClient(transport)
    assert await client.connect()
    try:
        transport.push(build_frame(0x0A, b"\xbf\x99", b"\x01"))
        await asyncio.sleep(0.1)
        assert client.unknown_messages >= 1
    finally:
        await client.disconnect()


async def test_filter_cycles_are_stored(handshake_frames: list[bytes]) -> None:
    transport = FakeTransport(handshake_frames)
    client = SpaClient(transport)
    assert await client.connect()
    try:
        cycles = _frames_of("ew11_probe", (FilterCycles,), 1)
        assert cycles, "the capture should contain a filter cycles response"
        transport.push(cycles[0])
        await asyncio.sleep(0.1)
        assert client.state.filter_cycles is not None
    finally:
        await client.disconnect()


async def test_mac_is_stored_when_it_does_arrive(
    handshake_frames: list[bytes],
) -> None:
    """This spa never sends one, but Wi-Fi module owners will."""
    from balboa.framing import build_frame

    transport = FakeTransport(handshake_frames)
    client = SpaClient(transport)
    assert await client.connect()
    try:
        payload = bytes([0x02, 0x02, 0x80]) + bytes.fromhex("001527aabbcc") + bytes(16)
        transport.push(build_frame(0x0A, b"\xbf\x94", payload))
        await asyncio.sleep(0.1)
        assert client.state.mac_address == "00:15:27:aa:bb:cc"
    finally:
        await client.disconnect()


async def test_counters_are_exposed(handshake_frames: list[bytes]) -> None:
    transport = FakeTransport(handshake_frames)
    client = SpaClient(transport)
    assert await client.connect()
    try:
        assert client.frames_read >= 3
        assert client.crc_errors == 0
        assert client.description == "fake"
        assert client.connected
    finally:
        await client.disconnect()


def test_capture_replay_is_deterministic() -> None:
    """Parsing the same capture twice must give identical results."""
    raw = (FIXTURES / "ew11_idle.bin").read_bytes()
    first = [type(parse_frame(f)).__name__ for f in FrameReader().feed(raw)]
    second = [type(parse_frame(f)).__name__ for f in FrameReader().feed(raw)]
    assert first == second
