"""Serial transport for an RS-485 adapter attached directly to the host.

Requires `pyserial-asyncio-fast`, which Home Assistant already ships for other
integrations. The import is deferred so the rest of the library stays usable
without it.
"""

from __future__ import annotations

import asyncio
from typing import Any

from .base import Transport

__all__ = ["BAUD_RATE", "SerialTransport"]

#: The bus runs at 115200 8N1 -- not configurable on the controller side.
BAUD_RATE = 115200

_READ_SIZE = 4096


class SerialTransport(Transport):
    """Byte stream over a local serial port."""

    def __init__(self, device: str, baud_rate: int = BAUD_RATE) -> None:
        self._device = device
        self._baud_rate = baud_rate
        self._reader: asyncio.StreamReader | None = None
        self._writer: Any = None
        self.description = device

    @property
    def connected(self) -> bool:
        return self._writer is not None

    async def connect(self) -> None:
        try:
            from serial_asyncio_fast import open_serial_connection
        except ImportError as err:  # pragma: no cover - depends on the host
            raise ConnectionError(
                "serial support needs the 'pyserial-asyncio-fast' package"
            ) from err

        try:
            self._reader, self._writer = await open_serial_connection(
                url=self._device,
                baudrate=self._baud_rate,
                bytesize=8,
                parity="N",
                stopbits=1,
            )
        except Exception as err:
            self._reader = self._writer = None
            raise ConnectionError(f"cannot open {self._device}: {err}") from err

    async def read(self) -> bytes:
        if self._reader is None:
            raise ConnectionError("not connected")
        try:
            return await self._reader.read(_READ_SIZE)
        except Exception as err:
            raise ConnectionError(f"read failed: {err}") from err

    async def write(self, data: bytes) -> None:
        if self._writer is None:
            raise ConnectionError("not connected")
        try:
            self._writer.write(data)
            await self._writer.drain()
        except Exception as err:
            raise ConnectionError(f"write failed: {err}") from err

    async def close(self) -> None:
        writer, self._writer, self._reader = self._writer, None, None
        if writer is None:
            return
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass
