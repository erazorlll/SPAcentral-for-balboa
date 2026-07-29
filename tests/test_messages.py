"""Message parsing and command serialisation."""

from __future__ import annotations

import pytest
from balboa.const import HeatMode, TemperatureUnit, ToggleItem
from balboa.framing import checksum
from balboa.messages import (
    SetTemperatureMessage,
    StatusUpdate,
    ToggleItemMessage,
    UnknownMessage,
    parse_frame,
    request_control_configuration,
    set_temperature,
    set_time,
    toggle,
)

# Real status frames, taken verbatim from fixtures/ew11_panel.bin.
# Water 33.5 °C, target 33.0 °C, everything off.
STATUS_IDLE = bytes.fromhex(
    "7e20ffaf130000430e0b000003060b0c000002000000000000420000001e0000467e"
)
# The same spa one frame after pump 1 was switched on at the panel.
STATUS_PUMP = bytes.fromhex(
    "7e20ffaf130000430e0b000003060b0c020002000000000000420000001e0000427e"
)


def test_status_idle() -> None:
    status = parse_frame(STATUS_IDLE)
    assert isinstance(status, StatusUpdate)
    assert status.temperature_unit is TemperatureUnit.CELSIUS
    assert status.current_temperature == 33.5
    assert status.target_temperature == 33.0
    assert status.heat_mode is HeatMode.READY
    assert status.pumps[0] == 0
    assert status.circulation_pump is True
    assert status.heating is False


def test_status_with_running_pump() -> None:
    status = parse_frame(STATUS_PUMP)
    assert isinstance(status, StatusUpdate)
    # A single-speed pump reports 2, not 1 -- confirmed on real hardware.
    assert status.pumps[0] == 2


def test_truncated_status_is_not_fatal() -> None:
    """A short frame must degrade to Unknown rather than raise."""
    short = STATUS_IDLE[:10] + STATUS_IDLE[-2:]
    assert isinstance(parse_frame(short), UnknownMessage)


def test_unknown_type_is_reported_not_raised() -> None:
    frame = bytes.fromhex("7e050abf99007e")
    message = parse_frame(frame)
    assert isinstance(message, UnknownMessage)
    assert message.message_type == b"\xbf\x99"


def test_empty_frame_is_handled() -> None:
    assert isinstance(parse_frame(b"\x7e\x02\x7e"), UnknownMessage)


def test_toggle_round_trip() -> None:
    frame = toggle(ToggleItem.PUMP_1)
    message = parse_frame(frame)
    assert isinstance(message, ToggleItemMessage)
    assert message.item is ToggleItem.PUMP_1


def test_toggle_matches_the_frame_the_panel_sends() -> None:
    """Our pump toggle must be byte-identical to the panel's, apart from channel."""
    ours = toggle(ToggleItem.PUMP_1)
    panel = bytes.fromhex("7e0710bf1104006a7e")
    assert ours[3:-2] == panel[3:-2]  # type and payload identical


def test_set_temperature_celsius_uses_half_degrees() -> None:
    frame = set_temperature(33.5, TemperatureUnit.CELSIUS)
    message = parse_frame(frame)
    assert isinstance(message, SetTemperatureMessage)
    assert message.raw_value == 67
    # matches a captured frame from the panel
    assert frame[3:-2] == bytes.fromhex("bf2043")


def test_set_temperature_fahrenheit_is_whole_degrees() -> None:
    frame = set_temperature(102, TemperatureUnit.FAHRENHEIT)
    message = parse_frame(frame)
    assert isinstance(message, SetTemperatureMessage)
    assert message.raw_value == 102


def test_set_temperature_rejects_out_of_range() -> None:
    with pytest.raises(ValueError, match="out of range"):
        set_temperature(200, TemperatureUnit.CELSIUS)


def test_set_time_encodes_the_24h_flag() -> None:
    frame = set_time(14, 30, twenty_four_hour=True)
    assert frame[5] == 0x80 | 14
    assert frame[6] == 30


@pytest.mark.parametrize(("hour", "minute"), [(24, 0), (-1, 0), (0, 60)])
def test_set_time_rejects_invalid(hour: int, minute: int) -> None:
    with pytest.raises(ValueError, match="invalid time"):
        set_time(hour, minute, twenty_four_hour=True)


def test_control_configuration_request_rejects_unknown_kind() -> None:
    with pytest.raises(ValueError, match="unknown control configuration"):
        request_control_configuration(9)


@pytest.mark.parametrize("index", [0, 1, 5])
def test_pump_toggle_codes(index: int) -> None:
    assert ToggleItem.pump(index) == ToggleItem.PUMP_1 + index


@pytest.mark.parametrize("index", [-1, 6])
def test_pump_toggle_code_rejects_bad_index(index: int) -> None:
    with pytest.raises(ValueError, match="pump index"):
        ToggleItem.pump(index)


# The real filter cycle configuration of the spa this was built against.
FILTER_CYCLES = bytes.fromhex("7e0d0abf23080005008e000800137e")


def test_filter_cycles_decode() -> None:
    from balboa.messages import FilterCycles

    cycles = parse_frame(FILTER_CYCLES)
    assert isinstance(cycles, FilterCycles)
    assert cycles.start(1) == (8, 0)
    assert cycles.duration(1) == 300  # five hours
    assert cycles.cycle_2_enabled is True
    assert cycles.start(2) == (14, 0)
    assert cycles.duration(2) == 480


def test_filter_cycles_round_trip() -> None:
    """Writing back what we read must reproduce the frame byte for byte."""
    from balboa.messages import set_filter_cycles

    cycles = parse_frame(FILTER_CYCLES)
    assert set_filter_cycles(cycles) == FILTER_CYCLES


def test_changing_a_start_leaves_everything_else() -> None:
    from balboa.messages import set_filter_cycles

    cycles = parse_frame(FILTER_CYCLES).with_start(1, 9, 30)
    payload = set_filter_cycles(cycles)[5:-2]
    assert payload[0:2] == bytes([9, 30])
    assert payload[2:4] == bytes([5, 0])  # duration untouched
    assert payload[4] == 0x8E  # cycle 2 untouched, still enabled


def test_duration_is_split_into_hours_and_minutes() -> None:
    from balboa.messages import set_filter_cycles

    cycles = parse_frame(FILTER_CYCLES).with_duration(2, 90)
    payload = set_filter_cycles(cycles)[5:-2]
    assert payload[6:8] == bytes([1, 30])


def test_disabling_cycle_two_keeps_its_start_hour() -> None:
    """The enable flag shares a byte with the hour, so it must not clobber it."""
    from dataclasses import replace

    from balboa.messages import set_filter_cycles

    cycles = replace(parse_frame(FILTER_CYCLES), cycle_2_enabled=False)
    payload = set_filter_cycles(cycles)[5:-2]
    assert payload[4] == 0x0E  # hour 14, flag cleared


def test_negative_duration_is_clamped() -> None:
    cycles = parse_frame(FILTER_CYCLES).with_duration(1, -60)
    assert cycles.duration(1) == 0


# The three fault log answers captured from the real controller.
FAULT_ENTRY_0 = bytes.fromhex("7e0f0abf28980013ff0c001842434370 7e".replace(" ", ""))
FAULT_ENTRY_1 = bytes.fromhex("7e0f0abf28980113ff0c00184243430 97e".replace(" ", ""))


def test_fault_log_request_matches_the_captured_frames() -> None:
    """Byte for byte what the capture tool sent and got an answer to."""
    from balboa.messages import request_fault_log

    assert request_fault_log(0).hex() == "7e080abf222000001c7e"
    assert request_fault_log(1).hex() == "7e080abf22200100097e"


def test_fault_log_entry_number_is_the_second_payload_byte() -> None:
    """The first byte is a selector shared with the other requests.

    Putting an index there would ask for the filter cycles instead, which is
    exactly the mistake the captures ruled out.
    """
    from balboa.messages import request_fault_log

    assert request_fault_log(0)[5:8] == bytes([0x20, 0x00, 0x00])
    assert request_fault_log(7)[5:8] == bytes([0x20, 0x07, 0x00])


def test_fault_log_request_rejects_out_of_range() -> None:
    from balboa.messages import request_fault_log

    with pytest.raises(ValueError, match="out of range"):
        request_fault_log(300)


def test_fault_log_entry_decodes() -> None:
    from balboa.messages import FaultLogEntry

    fault = parse_frame(FAULT_ENTRY_0)
    assert isinstance(fault, FaultLogEntry)
    assert fault.entry == 0
    assert fault.code == 19
    assert fault.name == "priming_mode"
    assert fault.counter == 152
    assert fault.days_ago == 255
    assert (fault.hour, fault.minute) == (12, 0)


def test_fault_log_temperatures_follow_the_spa_unit() -> None:
    """Confirmed by the capture: these matched the spa's live values."""
    fault = parse_frame(FAULT_ENTRY_0)

    target, sensor_a, sensor_b = fault.temperatures(TemperatureUnit.CELSIUS)
    assert (target, sensor_a, sensor_b) == (33.0, 33.5, 33.5)

    target_f, _, _ = fault.temperatures(TemperatureUnit.FAHRENHEIT)
    assert target_f == 66.0


def test_fault_log_echoes_the_requested_entry() -> None:
    assert parse_frame(FAULT_ENTRY_0).entry == 0
    assert parse_frame(FAULT_ENTRY_1).entry == 1


def test_unknown_fault_code_is_not_hidden() -> None:
    raw = bytearray(FAULT_ENTRY_0)
    raw[7] = 99  # a code we have no wording for
    raw[-2] = checksum(bytes(raw[1:-2]))
    fault = parse_frame(bytes(raw))
    assert fault.name == "code_99"


def test_truncated_fault_log_is_not_fatal() -> None:
    from balboa.messages import UnknownMessage

    short = FAULT_ENTRY_0[:9] + FAULT_ENTRY_0[-2:]
    assert isinstance(parse_frame(short), UnknownMessage)
