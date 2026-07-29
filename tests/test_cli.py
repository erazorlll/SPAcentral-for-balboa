"""The command line front end -- the acceptance harness for the library."""

from __future__ import annotations

from dataclasses import replace

import pytest
from balboa.__main__ import _render, main
from balboa.const import Notification, TemperatureUnit
from balboa.messages import ControlConfiguration, ControlConfiguration2, parse_frame
from balboa.state import SpaState

STATUS_IDLE = bytes.fromhex(
    "7e20ffaf130000430e0b000003060b0c000002000000000000420000001e0000467e"
)
STATUS_PUMP = bytes.fromhex(
    "7e20ffaf130000430e0b000003060b0c020002000000000000420000001e0000427e"
)


@pytest.fixture
def full_state() -> SpaState:
    return SpaState(
        status=parse_frame(STATUS_IDLE),
        control_configuration=ControlConfiguration(
            channel=0x0A, raw=b"", model="BP6013G3", software_id="64e2", version="43.0"
        ),
        hardware=ControlConfiguration2(
            channel=0x0A,
            raw=b"",
            pumps=(1, 1, 1, 0, 0, 0),
            lights=(True, False),
            aux=(False, False),
            blower_speeds=1,
            circulation_pump=True,
            mister=False,
        ),
    )


def test_render_without_data() -> None:
    assert "waiting" in _render(SpaState(), available=True)


def test_render_shows_the_essentials(full_state: SpaState) -> None:
    output = _render(full_state, available=True)
    assert "BP6013G3" in output
    assert "43.0" in output
    assert "33.5 °C" in output
    assert "33 °C" in output
    assert "idle" in output
    assert "pump1=off" in output
    assert "light1=off" in output
    assert "circ=on" in output
    # absent hardware must not be listed
    assert "pump4" not in output
    assert "mister" not in output
    assert "aux" not in output


def test_render_marks_a_running_pump(full_state: SpaState) -> None:
    state = full_state.with_status(parse_frame(STATUS_PUMP))
    assert "pump1=on" in _render(state, available=True)


def test_render_flags_stale_data(full_state: SpaState) -> None:
    assert "stale" in _render(full_state, available=False)


def test_render_shows_notifications(full_state: SpaState) -> None:
    status = full_state.status
    assert status is not None
    state = full_state.with_status(replace(status, notification=Notification.FILTER))
    assert "notification: filter" in _render(state, available=True)


def test_render_shows_a_mac_when_known(full_state: SpaState) -> None:
    state = full_state.with_mac("00:15:27:aa:bb:cc")
    assert "00:15:27:aa:bb:cc" in _render(state, available=True)


def test_render_handles_fahrenheit(full_state: SpaState) -> None:
    status = full_state.status
    assert status is not None
    state = full_state.with_status(
        replace(status, temperature_unit=TemperatureUnit.FAHRENHEIT)
    )
    assert "°F" in _render(state, available=True)


def test_render_shows_multi_speed_pump_level(full_state: SpaState) -> None:
    hardware = full_state.hardware
    status = full_state.status
    assert hardware is not None and status is not None
    state = SpaState(
        status=replace(status, pumps=(1, 0, 0, 0, 0, 0)),
        hardware=replace(hardware, pumps=(2, 0, 0, 0, 0, 0)),
        control_configuration=full_state.control_configuration,
    )
    assert "pump1=1" in _render(state, available=True)


def test_main_requires_a_target() -> None:
    with pytest.raises(SystemExit):
        main([])


def test_main_discover_reports_nothing_found(monkeypatch: pytest.MonkeyPatch) -> None:
    async def no_spas(timeout: float = 5.0) -> list:
        return []

    monkeypatch.setattr("balboa.__main__.async_discover", no_spas)
    assert main(["--discover"]) == 1


def test_main_discover_lists_findings(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from balboa.discovery import DiscoveredSpa

    async def one_spa(timeout: float = 5.0) -> list[DiscoveredSpa]:
        return [DiscoveredSpa("10.0.0.5", "BWGSPA", "00:15:27:aa:bb:cc")]

    monkeypatch.setattr("balboa.__main__.async_discover", one_spa)
    assert main(["--discover"]) == 0
    assert "10.0.0.5" in capsys.readouterr().out


def test_main_reports_a_failed_connection() -> None:
    """Port 1 on loopback refuses, so this exercises the failure path."""
    assert main(["127.0.0.1", "--port", "1"]) == 1
