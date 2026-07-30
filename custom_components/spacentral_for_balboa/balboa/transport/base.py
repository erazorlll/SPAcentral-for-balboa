"""Transport abstraction.

Everything above this layer works on frames and never learns whether they
arrived over a socket, a serial port or anything added later.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

__all__ = ["Transport"]


class Transport(ABC):
    """A bidirectional byte stream to a spa controller."""

    #: Shown in logs and diagnostics, e.g. "10.0.0.9:8899" or "/dev/ttyUSB0".
    description: str

    @abstractmethod
    async def connect(self) -> None:
        """Open the connection. Raises `ConnectionError` on failure."""

    @abstractmethod
    async def read(self) -> bytes:
        """Return the next chunk of bytes.

        Returns an empty bytes object when the peer closed the connection.
        """

    @abstractmethod
    async def write(self, data: bytes) -> None:
        """Send bytes. Raises `ConnectionError` if the link is gone."""

    @abstractmethod
    async def close(self) -> None:
        """Close the connection. Must be safe to call more than once."""

    @property
    @abstractmethod
    def connected(self) -> bool:
        """Whether the transport currently holds an open connection."""
