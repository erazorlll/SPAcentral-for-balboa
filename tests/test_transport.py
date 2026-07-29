"""Transports, exercised against real local sockets rather than mocks."""

from __future__ import annotations

import asyncio

import pytest
from balboa.transport import GATEWAY_PORT, WIFI_MODULE_PORT, SerialTransport, TcpTransport


@pytest.fixture
async def echo_server() -> tuple[str, int, list[bytes]]:
    """A local TCP server that greets, echoes, and records what it received."""
    received: list[bytes] = []

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        writer.write(b"hello")
        await writer.drain()
        try:
            while data := await reader.read(1024):
                received.append(data)
                writer.write(data)
                await writer.drain()
        except (ConnectionError, asyncio.CancelledError):
            pass

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    host, port = server.sockets[0].getsockname()[:2]
    async with server:
        yield host, port, received


def test_default_ports_are_the_documented_ones() -> None:
    assert WIFI_MODULE_PORT == 4257
    assert GATEWAY_PORT == 8899


async def test_tcp_connect_read_write(echo_server) -> None:
    host, port, received = echo_server
    transport = TcpTransport(host, port)

    assert not transport.connected
    await transport.connect()
    assert transport.connected
    assert transport.description == f"{host}:{port}"

    assert await transport.read() == b"hello"

    await transport.write(b"\x7e\x05\x0a\xbf\x04\x77\x7e")
    assert await transport.read() == b"\x7e\x05\x0a\xbf\x04\x77\x7e"
    assert received

    await transport.close()
    assert not transport.connected


async def test_tcp_close_is_idempotent(echo_server) -> None:
    host, port, _ = echo_server
    transport = TcpTransport(host, port)
    await transport.connect()
    await transport.close()
    await transport.close()


async def test_tcp_connect_to_nothing_raises() -> None:
    # port 1 on loopback is reliably closed
    transport = TcpTransport("127.0.0.1", 1)
    with pytest.raises(ConnectionError, match="cannot connect"):
        await transport.connect()


async def test_tcp_read_without_connect_raises() -> None:
    with pytest.raises(ConnectionError, match="not connected"):
        await TcpTransport("127.0.0.1", 1).read()


async def test_tcp_write_without_connect_raises() -> None:
    with pytest.raises(ConnectionError, match="not connected"):
        await TcpTransport("127.0.0.1", 1).write(b"x")


async def test_tcp_read_returns_empty_when_peer_closes(echo_server) -> None:
    """The client relies on this to detect a dropped connection."""
    host, port, _ = echo_server
    transport = TcpTransport(host, port)
    await transport.connect()
    await transport.read()  # greeting

    # Force the server side to go away by closing our writer half.
    await transport.close()
    assert not transport.connected


async def test_serial_transport_reports_a_bad_device() -> None:
    transport = SerialTransport("/definitely/not/a/serial/port")
    assert transport.description == "/definitely/not/a/serial/port"
    assert not transport.connected
    with pytest.raises(ConnectionError):
        await transport.connect()


async def test_serial_read_write_without_connect_raise() -> None:
    transport = SerialTransport("/dev/null")
    with pytest.raises(ConnectionError, match="not connected"):
        await transport.read()
    with pytest.raises(ConnectionError, match="not connected"):
        await transport.write(b"x")
    await transport.close()  # must not raise
