"""Frame assembly, checksum and resynchronisation."""

from __future__ import annotations

import pytest
from balboa.const import CLIENT_CHANNEL, MessageType
from balboa.framing import FrameReader, build_frame, checksum

# Captured from real hardware -- the four requests the client sends on connect.
REAL_FRAMES = {
    "configuration_request": "7e050abf04777e",
    "control_config_1": "7e080abf22020000897e",
    "control_config_2": "7e080abf22000001587e",
    "filter_cycles": "7e080abf22010000347e",
    # observed on the bus, sent by the control panel
    "toggle_pump1": "7e0710bf1104006a7e",
    "toggle_light1": "7e0710bf1111007c7e",
    "set_temperature": "7e0610bf2043277e",
}


@pytest.mark.parametrize(("name", "hex_frame"), REAL_FRAMES.items())
def test_checksum_matches_real_frames(name: str, hex_frame: str) -> None:
    """Our CRC must reproduce the byte the controller and panel actually sent."""
    frame = bytes.fromhex(hex_frame)
    assert checksum(frame[1:-2]) == frame[-2], name


def test_build_frame_reproduces_captured_request() -> None:
    built = build_frame(CLIENT_CHANNEL, MessageType.CONFIGURATION_REQUEST.value)
    assert built.hex() == REAL_FRAMES["configuration_request"]


def test_build_frame_with_payload() -> None:
    built = build_frame(
        CLIENT_CHANNEL, MessageType.CONTROL_CONFIGURATION_REQUEST.value, b"\x02\x00\x00"
    )
    assert built.hex() == REAL_FRAMES["control_config_1"]


def test_reader_accepts_a_whole_frame() -> None:
    reader = FrameReader()
    frames = reader.feed(bytes.fromhex(REAL_FRAMES["toggle_pump1"]))
    assert len(frames) == 1
    assert reader.crc_errors == 0
    assert reader.discarded_bytes == 0


def test_reader_reassembles_a_split_frame() -> None:
    """A frame arriving in two reads must still be recognised."""
    raw = bytes.fromhex(REAL_FRAMES["toggle_pump1"])
    reader = FrameReader()
    assert reader.feed(raw[:4]) == []
    assert reader.feed(raw[4:]) == [raw]


def test_reader_skips_leading_junk() -> None:
    """Captures routinely start mid-frame."""
    raw = bytes.fromhex(REAL_FRAMES["toggle_light1"])
    reader = FrameReader()
    assert reader.feed(b"\x11\x22\x33" + raw) == [raw]
    assert reader.discarded_bytes == 3


def test_reader_rejects_bad_checksum() -> None:
    raw = bytearray.fromhex(REAL_FRAMES["toggle_pump1"])
    raw[-2] ^= 0xFF
    reader = FrameReader()
    assert reader.feed(bytes(raw)) == []
    assert reader.crc_errors == 1


def test_reader_recovers_after_a_corrupt_frame() -> None:
    """One damaged frame must not swallow the next good one."""
    bad = bytearray.fromhex(REAL_FRAMES["toggle_pump1"])
    bad[-2] ^= 0xFF
    good = bytes.fromhex(REAL_FRAMES["toggle_light1"])

    reader = FrameReader()
    frames = reader.feed(bytes(bad) + good)
    assert frames == [good]
    assert reader.crc_errors == 1


def test_reader_ignores_implausible_length() -> None:
    reader = FrameReader()
    assert reader.feed(b"\x7e\xff\x00\x00") == []
    assert reader.frames_read == 0


def test_reader_handles_byte_at_a_time() -> None:
    """The pathological case: one byte per read."""
    raw = bytes.fromhex(REAL_FRAMES["set_temperature"])
    reader = FrameReader()
    out: list[bytes] = []
    for byte in raw:
        out.extend(reader.feed(bytes([byte])))
    assert out == [raw]


def test_reset_drops_partial_data() -> None:
    reader = FrameReader()
    reader.feed(bytes.fromhex(REAL_FRAMES["toggle_pump1"])[:3])
    reader.reset()
    assert reader.feed(bytes.fromhex(REAL_FRAMES["toggle_pump1"])) != []
