"""Discovery, driven against a local UDP responder.

The real thing only answers on a Balboa Wi-Fi module, which is not available
here -- so the responder imitates the documented reply format.
"""

from __future__ import annotations

import asyncio

import pytest
from balboa.discovery import (
    BALBOA_OUI,
    DISCOVERY_MESSAGE,
    DISCOVERY_PORT,
    _DiscoveryProtocol,
    async_discover,
)


def test_oui_matches_the_dhcp_matcher() -> None:
    """Home Assistant's manifest uses 001527*; keep the two in step."""
    assert BALBOA_OUI.replace(":", "") == "001527"


def _feed(payload: bytes, host: str = "10.0.0.5") -> dict:
    protocol = _DiscoveryProtocol()
    protocol.datagram_received(payload, (host, DISCOVERY_PORT))
    return protocol.results


def test_valid_reply_is_accepted() -> None:
    results = _feed(b"BWGSPA\r\n00-15-27-AA-BB-CC\r\n")
    assert list(results) == ["10.0.0.5"]
    spa = results["10.0.0.5"]
    assert spa.hostname == "BWGSPA"
    assert spa.mac_address == "00:15:27:aa:bb:cc"


def test_reply_from_another_vendor_is_ignored() -> None:
    """Other devices answer this broadcast too; they must not show up."""
    assert _feed(b"SOMETHING\r\nAA-BB-CC-DD-EE-FF\r\n") == {}


def test_malformed_replies_are_ignored() -> None:
    assert _feed(b"") == {}
    assert _feed(b"only one line") == {}
    assert _feed(b"\xff\xfe\xfd") == {}


def test_duplicate_replies_collapse_per_host() -> None:
    protocol = _DiscoveryProtocol()
    for _ in range(3):
        protocol.datagram_received(b"BWGSPA\r\n00-15-27-AA-BB-CC\r\n", ("10.0.0.5", 1))
    assert len(protocol.results) == 1


async def test_discover_returns_nothing_when_no_one_answers() -> None:
    assert await async_discover(timeout=0.05) == []


async def test_discover_collects_a_local_responder() -> None:
    """Bind a fake module on the discovery port and make sure we hear it."""

    class Responder(asyncio.DatagramProtocol):
        def __init__(self) -> None:
            self.transport: asyncio.DatagramTransport | None = None

        def connection_made(self, transport) -> None:  # type: ignore[no-untyped-def]
            self.transport = transport

        def datagram_received(self, data: bytes, addr) -> None:  # type: ignore[no-untyped-def]
            if data == DISCOVERY_MESSAGE and self.transport:
                self.transport.sendto(b"BWGSPA\r\n00-15-27-11-22-33\r\n", addr)

    loop = asyncio.get_running_loop()
    try:
        transport, _ = await loop.create_datagram_endpoint(
            Responder, local_addr=("0.0.0.0", DISCOVERY_PORT)
        )
    except OSError:
        pytest.skip("cannot bind the discovery port in this environment")

    try:
        found = await async_discover(timeout=0.5)
    finally:
        transport.close()

    assert any(spa.mac_address == "00:15:27:11:22:33" for spa in found)
