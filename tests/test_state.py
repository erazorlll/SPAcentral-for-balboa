"""SpaState accessors, including the empty and out-of-range cases.

Entities ask these questions before any data has arrived, so every accessor has
to answer sensibly on an empty state rather than raise.
"""

from __future__ import annotations

import pytest
from balboa.const import MAX_AUX, MAX_LIGHTS, MAX_PUMPS
from balboa.messages import ControlConfiguration, ControlConfiguration2, parse_frame
from balboa.state import SpaState, manual_hardware

STATUS = bytes.fromhex(
    "7e20ffaf130000430e0b000003060b0c000002000000000000420000001e0000467e"
)


@pytest.fixture
def hardware() -> ControlConfiguration2:
    """Three single-speed pumps, one light, blower, circulation pump."""
    return ControlConfiguration2(
        channel=0x0A,
        raw=b"",
        pumps=(1, 1, 1, 0, 0, 0),
        lights=(True, False),
        aux=(False, False),
        blower_speeds=1,
        circulation_pump=True,
        mister=False,
    )


def test_empty_state_is_not_ready() -> None:
    state = SpaState()
    assert not state.ready
    assert state.model == "Balboa Spa"
    assert state.software_version is None
    assert state.mac_address is None


def test_empty_state_answers_every_accessor() -> None:
    state = SpaState()
    assert state.pump_speeds(0) == 0
    assert state.pump_state(0) == 0
    assert state.is_pump_on(0) is False
    assert state.is_light_on(0) is False
    assert state.is_aux_on(0) is False
    assert state.has_light(0) is False
    assert state.has_aux(0) is False
    assert state.has_circulation_pump is False
    assert state.has_mister is False
    assert state.blower_speeds == 0


@pytest.mark.parametrize("index", [-1, 6, 99])
def test_out_of_range_indices_are_safe(
    index: int, hardware: ControlConfiguration2
) -> None:
    state = SpaState(hardware=hardware, status=parse_frame(STATUS))
    assert state.pump_speeds(index) == 0
    assert state.pump_state(index) == 0
    assert state.is_pump_on(index) is False
    assert state.has_light(index) is False
    assert state.is_light_on(index) is False
    assert state.has_aux(index) is False
    assert state.is_aux_on(index) is False


def test_ready_needs_status_and_hardware(hardware: ControlConfiguration2) -> None:
    """Deliberately does not require the MAC-bearing configuration response."""
    assert not SpaState(status=parse_frame(STATUS)).ready
    assert not SpaState(hardware=hardware).ready
    assert SpaState(status=parse_frame(STATUS), hardware=hardware).ready


def test_model_falls_back_when_unknown() -> None:
    config = ControlConfiguration(
        channel=0x0A, raw=b"", model="", software_id="0000", version="1.0"
    )
    assert SpaState(control_configuration=config).model == "Balboa Spa"


def test_with_helpers_return_new_instances(hardware: ControlConfiguration2) -> None:
    """The state is frozen; updates must not mutate in place."""
    original = SpaState()
    updated = original.with_hardware(hardware)
    assert original.hardware is None
    assert updated.hardware is hardware

    assert original.with_mac(None) is original
    assert original.with_mac("00:15:27:aa:bb:cc").mac_address == "00:15:27:aa:bb:cc"


def test_manual_hardware_fills_the_leading_slots() -> None:
    """Counts turn into "the first N are fitted", everything else absent."""
    built = manual_hardware(
        pump_count=2,
        light_count=1,
        aux_count=0,
        has_blower=True,
        has_circulation_pump=True,
        has_mister=False,
    )
    assert built.pumps == (1, 1) + (0,) * (MAX_PUMPS - 2)
    assert built.lights == (True,) + (False,) * (MAX_LIGHTS - 1)
    assert built.aux == (False,) * MAX_AUX
    assert built.blower_speeds == 1
    assert built.circulation_pump is True
    assert built.mister is False


def test_manual_hardware_pumps_and_blower_are_always_single_speed() -> None:
    """Never guess a 2-speed pump: see `manual_hardware`'s docstring for why a
    wrong guess risks physically toggling real hardware, not just a UI glitch."""
    built = manual_hardware(
        pump_count=MAX_PUMPS,
        light_count=0,
        aux_count=0,
        has_blower=True,
        has_circulation_pump=False,
        has_mister=False,
    )
    assert set(built.pumps) == {1}
    assert built.blower_speeds == 1


def test_manual_hardware_plugs_into_state_like_the_real_thing() -> None:
    """The synthesized descriptor must satisfy the same accessors as a real one."""
    built = manual_hardware(
        pump_count=1,
        light_count=1,
        aux_count=1,
        has_blower=False,
        has_circulation_pump=False,
        has_mister=False,
    )
    state = SpaState(status=parse_frame(STATUS), hardware=built)
    assert state.ready
    assert state.pump_speeds(0) == 1
    assert state.has_light(0) is True
    assert state.has_aux(0) is True
    assert state.blower_speeds == 0


def test_single_speed_pump_reports_two_when_on(hardware: ControlConfiguration2) -> None:
    """The finding from the captures, pinned down here."""
    pump_running = bytes.fromhex(
        "7e20ffaf130000430e0b000003060b0c020002000000000000420000001e0000427e"
    )
    state = SpaState(status=parse_frame(pump_running), hardware=hardware)
    assert state.pump_speeds(0) == 1  # one speed fitted
    assert state.pump_state(0) == 2  # but reported as 2
    assert state.is_pump_on(0) is True
