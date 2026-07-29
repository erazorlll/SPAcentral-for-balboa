"""The important tests: run the parser over 34,616 frames of real traffic.

Synthetic data would hide exactly the surprises these captures contain -- for
instance that a single-speed pump reports 2 when running, or that this
controller never answers the request carrying a MAC address.
"""

from __future__ import annotations

from collections import Counter

from balboa.const import HeatMode, TemperatureRange, TemperatureUnit
from balboa.framing import FrameReader
from balboa.messages import (
    ControlConfiguration,
    ControlConfiguration2,
    FilterCycles,
    ModuleConfiguration,
    NewClientClearToSendMessage,
    NothingToSendMessage,
    ReadyMessage,
    StatusUpdate,
    UnknownMessage,
    parse_frame,
)


def _parse_all(raw: bytes) -> tuple[FrameReader, list]:
    reader = FrameReader()
    return reader, [parse_frame(frame) for frame in reader.feed(raw)]


def test_idle_capture_parses_without_crc_errors(capture_idle: bytes) -> None:
    reader, messages = _parse_all(capture_idle)
    assert reader.frames_read > 10_000
    assert reader.crc_errors == 0
    # only the partial frame the capture started in the middle of
    assert reader.discarded_bytes < 20
    assert len(messages) == reader.frames_read


def test_every_capture_is_clean(
    capture_idle: bytes, capture_probe: bytes, capture_panel: bytes
) -> None:
    total = 0
    for raw in (capture_idle, capture_probe, capture_panel):
        reader, _ = _parse_all(raw)
        assert reader.crc_errors == 0
        total += reader.frames_read
    assert total > 34_000


def test_no_unknown_message_types(
    capture_idle: bytes, capture_probe: bytes, capture_panel: bytes
) -> None:
    """Everything this controller emits must be modelled."""
    unknown: Counter[bytes] = Counter()
    for raw in (capture_idle, capture_probe, capture_panel):
        _, messages = _parse_all(raw)
        for message in messages:
            if isinstance(message, UnknownMessage):
                unknown[message.message_type] += 1
    assert not unknown, f"unmodelled types: {[t.hex() for t in unknown]}"


def test_bus_composition(capture_idle: bytes) -> None:
    """An undisturbed bus is almost entirely arbitration traffic."""
    _, messages = _parse_all(capture_idle)
    kinds = Counter(type(message).__name__ for message in messages)

    assert kinds[ReadyMessage.__name__] > 5_000
    assert kinds[NothingToSendMessage.__name__] > 5_000
    assert kinds[StatusUpdate.__name__] > 300
    assert kinds[NewClientClearToSendMessage.__name__] > 50


def test_ready_tokens_are_not_addressed_to_us(capture_idle: bytes) -> None:
    """The design hinges on this: the send token belongs to the control panel.

    If we ever waited for a Ready on our own channel we would never transmit.
    """
    _, messages = _parse_all(capture_idle)
    channels = {m.channel for m in messages if isinstance(m, ReadyMessage)}
    assert channels == {0x10}


def test_status_decodes_consistently(capture_idle: bytes) -> None:
    _, messages = _parse_all(capture_idle)
    statuses = [m for m in messages if isinstance(m, StatusUpdate)]
    assert statuses

    for status in statuses:
        assert status.temperature_unit is TemperatureUnit.CELSIUS
        assert status.twenty_four_hour_time is True
        assert status.heat_mode is HeatMode.READY
        assert status.temperature_range is TemperatureRange.HIGH
        assert status.circulation_pump is True
        assert 0 <= status.hour < 24
        assert 0 <= status.minute < 60
        assert status.current_temperature == 33.5
        assert status.target_temperature == 33.0


def test_probe_answers_control_configuration(capture_probe: bytes) -> None:
    """The three control configuration requests are answered."""
    _, messages = _parse_all(capture_probe)
    assert any(isinstance(m, ControlConfiguration) for m in messages)
    assert any(isinstance(m, ControlConfiguration2) for m in messages)
    assert any(isinstance(m, FilterCycles) for m in messages)


def test_probe_never_yields_a_mac(capture_probe: bytes) -> None:
    """The core finding of phase 0, locked down as a test.

    This controller ignores the configuration request entirely, so no MAC is
    available. Libraries that require one cannot set this spa up at all.
    """
    _, messages = _parse_all(capture_probe)
    configs = [m for m in messages if isinstance(m, ModuleConfiguration)]
    assert configs == []


def test_hardware_configuration_matches_the_spa(capture_probe: bytes) -> None:
    _, messages = _parse_all(capture_probe)
    hardware = next(m for m in messages if isinstance(m, ControlConfiguration2))

    assert hardware.pumps == (1, 1, 1, 0, 0, 0)  # three single-speed pumps
    assert hardware.pump_count == 3
    assert hardware.lights == (True, False)
    assert hardware.blower_speeds == 1
    assert hardware.circulation_pump is True
    assert hardware.mister is False
    assert hardware.aux == (False, False)


def test_model_is_read_from_control_configuration(capture_probe: bytes) -> None:
    _, messages = _parse_all(capture_probe)
    config = next(m for m in messages if isinstance(m, ControlConfiguration))
    assert config.model == "BP6013G3"
    assert config.version == "43.0"


def test_panel_actions_are_visible_in_the_status(capture_panel: bytes) -> None:
    """Operating the panel must show up as state changes we can follow."""
    _, messages = _parse_all(capture_panel)
    statuses = [m for m in messages if isinstance(m, StatusUpdate)]

    pump_values = {status.pumps[0] for status in statuses}
    assert pump_values == {0, 2}, "a single-speed pump reports 2 when on, never 1"

    assert {status.lights[0] for status in statuses} == {False, True}
    assert {status.target_temperature for status in statuses} >= {33.0, 33.5, 34.0}
