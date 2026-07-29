"""Frame level of the Balboa protocol: checksum, assembly, resynchronisation.

A frame looks like this::

    0x7e  LEN  CH  0xBF  TYPE  ...payload...  CRC  0x7e
          ^^^^ counts from itself up to and including the CRC minus one
          ^^^^ so the whole frame is LEN + 2 bytes

The CRC covers the bytes from LEN up to (not including) the CRC itself.
"""

from __future__ import annotations

from .const import (
    CRC_FINAL_XOR,
    CRC_INIT,
    CRC_POLYNOMIAL,
    DELIMITER,
    MAX_FRAME_LENGTH,
    MIN_FRAME_LENGTH,
)

__all__ = ["FrameReader", "build_frame", "checksum"]


def checksum(data: bytes) -> int:
    """CRC-8 as used by Balboa: poly 0x07, init 0x02, final XOR 0x02."""
    crc = CRC_INIT
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x80:
                crc = ((crc << 1) ^ CRC_POLYNOMIAL) & 0xFF
            else:
                crc = (crc << 1) & 0xFF
    return crc ^ CRC_FINAL_XOR


def build_frame(channel: int, message_type: bytes, payload: bytes = b"") -> bytes:
    """Assemble a complete frame ready to be written to the bus."""
    body = bytes([len(payload) + len(message_type) + 3, channel]) + message_type + payload
    return bytes([DELIMITER]) + body + bytes([checksum(body), DELIMITER])


class FrameReader:
    """Turns an arbitrarily chunked byte stream into validated frames.

    Deliberately forgiving: the RS-485 bus is shared, a capture can start
    mid-frame, and a serial line can drop bytes. Anything that does not parse is
    dropped and counted, never raised -- one bad byte must not take down the
    integration.
    """

    __slots__ = ("_buffer", "crc_errors", "discarded_bytes", "frames_read")

    def __init__(self) -> None:
        self._buffer = bytearray()
        self.crc_errors = 0
        self.discarded_bytes = 0
        self.frames_read = 0

    def feed(self, data: bytes) -> list[bytes]:
        """Add received bytes and return every complete frame found."""
        self._buffer.extend(data)
        frames: list[bytes] = []

        while True:
            start = self._buffer.find(DELIMITER)
            if start < 0:
                # No delimiter at all -- keep the last byte, it may be one.
                self.discarded_bytes += len(self._buffer)
                self._buffer.clear()
                break
            if start:
                self.discarded_bytes += start
                del self._buffer[:start]
            if len(self._buffer) < 2:
                break

            length = self._buffer[1]
            if not MIN_FRAME_LENGTH <= length <= MAX_FRAME_LENGTH:
                self._resync()
                continue

            total = length + 2
            if len(self._buffer) < total:
                break  # incomplete, wait for more

            frame = bytes(self._buffer[:total])
            if frame[-1] != DELIMITER:
                self._resync()
                continue
            if checksum(frame[1:-2]) != frame[-2]:
                self.crc_errors += 1
                self._resync()
                continue

            frames.append(frame)
            self.frames_read += 1
            del self._buffer[:total]

        return frames

    def reset(self) -> None:
        """Drop buffered data, e.g. after reconnecting."""
        self.discarded_bytes += len(self._buffer)
        self._buffer.clear()

    def _resync(self) -> None:
        """Skip one byte and look for the next delimiter."""
        self.discarded_bytes += 1
        del self._buffer[:1]
