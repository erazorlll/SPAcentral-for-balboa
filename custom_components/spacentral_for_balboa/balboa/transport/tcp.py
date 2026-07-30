"""TCP transport.

Serves both supported network setups; they differ only in the port number:

* the original Balboa Wi-Fi module, which listens on 4257
* an RS-485 gateway in TCP server mode (Elfin EW11, ser2net, ESPHome), usually 8899
"""

from __future__ import annotations

import asyncio
import contextlib

from .base import Transport

__all__ = ["GATEWAY_PORT", "WIFI_MODULE_PORT", "TcpTransport"]

#: Port of the original Balboa Wi-Fi module.
WIFI_MODULE_PORT = 4257
#: Common default of serial-to-network gateways in TCP server mode.
GATEWAY_PORT = 8899

_CONNECT_TIMEOUT = 10
_READ_SIZE = 4096


class TcpTransport(Transport):
    """Byte stream over a plain TCP connection."""

    def __init__(self, host: str, port: int = WIFI_MODULE_PORT) -> None:
        self._host = host
        self._port = port
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self.description = f"{host}:{port}"

    @property
    def connected(self) -> bool:
        return self._writer is not None and not self._writer.is_closing()

    async def connect(self) -> None:
        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self._host, self._port), _CONNECT_TIMEOUT
            )
        except (TimeoutError, OSError) as err:
            self._reader = self._writer = None
            raise ConnectionError(f"cannot connect to {self.description}: {err}") from err

    async def read(self) -> bytes:
        if self._reader is None:
            raise ConnectionError("not connected")
        try:
            return await self._reader.read(_READ_SIZE)
        except OSError as err:
            raise ConnectionError(f"read failed: {err}") from err

    async def write(self, data: bytes) -> None:
        if self._writer is None or self._writer.is_closing():
            raise ConnectionError("not connected")
        try:
            self._writer.write(data)
            await self._writer.drain()
        except OSError as err:
            raise ConnectionError(f"write failed: {err}") from err

    async def close(self) -> None:
        writer, self._writer, self._reader = self._writer, None, None
        if writer is None:
            return
        writer.close()
        # Closing is best effort: the peer may already be gone.
        with contextlib.suppress(OSError, asyncio.CancelledError):
            await writer.wait_closed()
