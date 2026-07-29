"""Asynchronous client: connection lifecycle, state assembly, commands."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import Callable
from random import uniform

from .const import (
    CELSIUS_DIVISOR,
    MAX_FAULT_LOG_ENTRIES,
    MAX_PUMPS,
    HeatMode,
    TemperatureRange,
    TemperatureUnit,
    ToggleItem,
)
from .framing import FrameReader
from .messages import (
    ControlConfiguration,
    ControlConfiguration2,
    FaultLogEntry,
    FilterCycles,
    ModuleConfiguration,
    StatusUpdate,
    UnknownMessage,
    parse_frame,
    request_configuration,
    request_control_configuration,
    request_fault_log,
    set_filter_cycles,
    set_temperature,
    set_temperature_unit,
    set_time,
    toggle,
)
from .state import SpaState
from .transport import Transport

_LOGGER = logging.getLogger(__name__)

__all__ = ["SpaClient"]

#: Status frames arrive roughly every 300 ms; the largest gap measured on real
#: hardware was 2.0 s. Five seconds is a safe margin that still notices a frozen
#: gateway quickly.
STALE_AFTER = 5.0
#: Give up on the connection entirely after this long without a frame.
RECONNECT_AFTER = 20.0
#: Wait at most this long for the initial configuration exchange.
CONFIGURATION_TIMEOUT = 20.0
#: How often the watchdog checks the frame clock.
MONITOR_INTERVAL = 1.0
#: First reconnect delay; doubles with every failed attempt.
INITIAL_BACKOFF = 1.0
#: Cap of the exponential reconnect backoff.
MAX_BACKOFF = 60.0

#: A toggle advances one step, so reaching a target speed can take several.
#: The spa needs a moment to report the new state between them.
TOGGLE_INTERVAL = 0.4
TOGGLE_LIMIT = 4
#: Spacing between the four configuration requests, so we do not flood the bus.
REQUEST_INTERVAL = 0.2
#: How often to re-read the fault log. It is 24 requests, and faults are rare,
#: so this is deliberately lazy. Re-reading the whole log also fills in
#: whatever the previous pass lost to a bus collision -- three of twenty-six
#: answers went missing in a measured sweep.
FAULT_LOG_INTERVAL = 1800.0
#: How often to re-ask for configuration pieces that never came back.
CONFIGURATION_RETRIES = 4
CONFIGURATION_RETRY_DELAY = 3.0


class SpaClient:
    """Talks to one spa controller.

    Usage::

        client = SpaClient(TcpTransport("10.0.0.9", 8899))
        await client.connect()
        client.subscribe(lambda: print(client.state.status))
    """

    def __init__(self, transport: Transport) -> None:
        self._transport = transport
        self._reader = FrameReader()
        self._state = SpaState()

        self._listeners: list[Callable[[], None]] = []
        self._reader_task: asyncio.Task[None] | None = None
        self._monitor_task: asyncio.Task[None] | None = None
        self._gap_task: asyncio.Task[None] | None = None
        self._fault_task: asyncio.Task[None] | None = None
        self._configured = asyncio.Event()
        self._shutdown = False

        self._last_frame_at: float = 0.0
        self._last_fault_request: float = 0.0
        self.unknown_messages = 0

    # ── Properties ───────────────────────────────────────────────────────────

    @property
    def state(self) -> SpaState:
        return self._state

    @property
    def description(self) -> str:
        return self._transport.description

    @property
    def connected(self) -> bool:
        return self._transport.connected

    @property
    def available(self) -> bool:
        """Connected *and* actually receiving data.

        A gateway can keep the socket open while the serial side has died; only
        the frame clock reveals that.
        """
        if not self._transport.connected or not self._last_frame_at:
            return False
        return time.monotonic() - self._last_frame_at < STALE_AFTER

    @property
    def frames_read(self) -> int:
        return self._reader.frames_read

    @property
    def crc_errors(self) -> int:
        return self._reader.crc_errors

    # ── Lifecycle ────────────────────────────────────────────────────────────

    async def connect(self) -> bool:
        """Connect and wait for the configuration. False if that did not work."""
        self._shutdown = False
        try:
            await self._transport.connect()
        except ConnectionError as err:
            _LOGGER.debug("connect failed: %s", err)
            return False

        self._start_tasks()
        await self._request_configuration()

        try:
            await asyncio.wait_for(self._configured.wait(), CONFIGURATION_TIMEOUT)
        except TimeoutError:
            _LOGGER.warning(
                "%s: no configuration within %.0fs (status=%s hardware=%s)",
                self.description,
                CONFIGURATION_TIMEOUT,
                self._state.status is not None,
                self._state.hardware is not None,
            )
            return False

        self._start_fault_sweep()
        return True

    async def disconnect(self) -> None:
        """Stop everything and close the connection."""
        self._shutdown = True
        tasks = (
            self._monitor_task,
            self._reader_task,
            self._gap_task,
            self._fault_task,
        )
        for task in tasks:
            if task is not None:
                task.cancel()
        for task in tasks:
            if task is not None:
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task
        self._monitor_task = self._reader_task = None
        self._gap_task = self._fault_task = None
        await self._transport.close()

    def subscribe(self, callback: Callable[[], None]) -> Callable[[], None]:
        """Register a listener for state changes; returns the unsubscribe hook."""
        self._listeners.append(callback)

        def unsubscribe() -> None:
            if callback in self._listeners:
                self._listeners.remove(callback)

        return unsubscribe

    # ── Commands ─────────────────────────────────────────────────────────────

    async def set_target_temperature(self, temperature: float) -> None:
        """Set the target temperature, in whatever unit the spa is using."""
        unit = self.temperature_unit
        await self._send(set_temperature(temperature, unit))

    async def set_temperature_unit(self, unit: TemperatureUnit) -> None:
        await self._send(set_temperature_unit(unit))

    async def set_clock(self, hour: int, minute: int) -> None:
        status = self._state.status
        await self._send(
            set_time(
                hour,
                minute,
                twenty_four_hour=status.twenty_four_hour_time if status else True,
            )
        )

    async def request_fault_log(self, entry: int = 0) -> None:
        """Ask for one fault log entry; the answer arrives asynchronously."""
        await self._send(request_fault_log(entry))

    async def read_fault_log(self) -> None:
        """Walk the whole log, one entry at a time.

        Answers are folded in as they arrive, so a lost one simply leaves the
        previous value in place until the next pass.
        """
        for entry in range(MAX_FAULT_LOG_ENTRIES):
            if self._shutdown or not self._transport.connected:
                return
            await self._send(request_fault_log(entry))
            await asyncio.sleep(REQUEST_INTERVAL)

    async def set_filter_cycles(self, cycles: FilterCycles) -> None:
        """Write both filter cycles, then ask for them back to confirm."""
        await self._send(set_filter_cycles(cycles))
        await asyncio.sleep(REQUEST_INTERVAL)
        await self._send(request_control_configuration(3))

    async def toggle_item(self, item: ToggleItem) -> None:
        await self._send(toggle(item))

    async def set_pump(self, index: int, speed: int) -> None:
        """Drive pump `index` to `speed` (0 = off).

        The protocol only offers a toggle that advances one step, so this issues
        as many toggles as needed and watches the reported state in between.
        """
        if not 0 <= index < MAX_PUMPS:
            raise ValueError(f"pump index out of range: {index}")
        speeds = self._state.pump_speeds(index)
        if speeds == 0:
            raise ValueError(f"pump {index + 1} is not fitted")

        item = ToggleItem.pump(index)
        for _ in range(TOGGLE_LIMIT):
            if self._pump_reached(index, speed, speeds):
                return
            await self._send(toggle(item))
            await asyncio.sleep(TOGGLE_INTERVAL)
        _LOGGER.debug(
            "%s: pump %d did not reach %s after %d toggles",
            self.description,
            index + 1,
            speed,
            TOGGLE_LIMIT,
        )

    def _pump_reached(self, index: int, wanted: int, speeds: int) -> bool:
        current = self._state.pump_state(index)
        if speeds == 1:
            # A single-speed pump reports 2 when running, so compare on/off only.
            return (current != 0) == (wanted != 0)
        return current == wanted

    async def set_light(self, index: int, on: bool) -> None:
        if self._state.is_light_on(index) != on:
            await self._send(toggle(ToggleItem.light(index)))

    async def set_aux(self, index: int, on: bool) -> None:
        if self._state.is_aux_on(index) != on:
            await self._send(toggle(ToggleItem.aux(index)))

    async def set_blower(self, speed: int) -> None:
        """Drive the blower to `speed`, toggling as needed."""
        speeds = self._state.blower_speeds
        if speeds == 0:
            raise ValueError("this spa has no blower")
        for _ in range(TOGGLE_LIMIT):
            current = self._state.status.blower if self._state.status else 0
            reached = (current != 0) == (speed != 0) if speeds == 1 else current == speed
            if reached:
                return
            await self._send(toggle(ToggleItem.BLOWER))
            await asyncio.sleep(TOGGLE_INTERVAL)

    async def set_heat_mode(self, mode: HeatMode) -> None:
        """Cycle the heating mode until it matches.

        READY_IN_REST is a transient state the controller enters on its own; it
        cannot be selected, so asking for it is rejected rather than looped on.
        """
        if mode is HeatMode.READY_IN_REST:
            raise ValueError("READY_IN_REST cannot be set, only observed")
        for _ in range(TOGGLE_LIMIT):
            if self._state.status and self._state.status.heat_mode is mode:
                return
            await self._send(toggle(ToggleItem.HEATING_MODE))
            await asyncio.sleep(TOGGLE_INTERVAL)

    async def set_temperature_range(self, temperature_range: TemperatureRange) -> None:
        for _ in range(TOGGLE_LIMIT):
            status = self._state.status
            if status and status.temperature_range is temperature_range:
                return
            await self._send(toggle(ToggleItem.TEMPERATURE_RANGE))
            await asyncio.sleep(TOGGLE_INTERVAL)

    @property
    def temperature_unit(self) -> TemperatureUnit:
        if self._state.status is None:
            return TemperatureUnit.CELSIUS
        return self._state.status.temperature_unit

    @property
    def temperature_step(self) -> float:
        """Smallest change the controller accepts."""
        if self.temperature_unit is TemperatureUnit.CELSIUS:
            return 1 / CELSIUS_DIVISOR
        return 1.0

    # ── Internals ────────────────────────────────────────────────────────────

    def _start_tasks(self) -> None:
        self._reader.reset()
        self._last_frame_at = time.monotonic()
        self._last_fault_request = time.monotonic()
        if self._reader_task is None or self._reader_task.done():
            self._reader_task = asyncio.create_task(self._read_loop())
        if self._monitor_task is None or self._monitor_task.done():
            self._monitor_task = asyncio.create_task(self._monitor_loop())
        if self._gap_task is None or self._gap_task.done():
            self._gap_task = asyncio.create_task(self._fill_configuration_gaps())

    def _start_fault_sweep(self) -> None:
        """Read the log in the background, once the handshake is done.

        It is 24 requests: inside the handshake they would add five seconds to
        it, and started alongside it they would interleave with the four that
        matter.
        """
        if self._fault_task is None or self._fault_task.done():
            self._fault_task = asyncio.create_task(self.read_fault_log())

    async def _request_configuration(self) -> None:
        """Ask for everything we need to build entities.

        The configuration request (the one carrying a MAC) is sent too, but an
        RS-485 setup without a Wi-Fi module never answers it -- that is expected
        and must not block the handshake.
        """
        for frame in (
            request_configuration(),
            request_control_configuration(1),
            request_control_configuration(2),
            request_control_configuration(3),
        ):
            try:
                await self._transport.write(frame)
            except ConnectionError as err:
                _LOGGER.debug("configuration request failed: %s", err)
                return
            await asyncio.sleep(REQUEST_INTERVAL)

    async def _fill_configuration_gaps(self) -> None:
        """Re-ask for whatever did not come back.

        We write without arbitration onto a bus the control panel is polling
        dozens of times a second, so a request or its answer can be lost in a
        collision -- observed on real hardware, where the model name went
        missing while the hardware description arrived. Only the pieces still
        absent are requested again.
        """
        for _ in range(CONFIGURATION_RETRIES):
            await asyncio.sleep(CONFIGURATION_RETRY_DELAY)
            if self._shutdown or not self._transport.connected:
                return

            missing: list[int] = []
            if self._state.control_configuration is None:
                missing.append(1)
            if self._state.hardware is None:
                missing.append(2)
            if self._state.filter_cycles is None:
                missing.append(3)
            if not missing:
                return

            _LOGGER.debug("%s: re-requesting configuration %s", self.description, missing)
            for kind in missing:
                await self._send(request_control_configuration(kind))
                await asyncio.sleep(REQUEST_INTERVAL)

    async def _send(self, frame: bytes) -> None:
        """Write a frame straight to the bus.

        No arbitration: the Ready tokens on an RS-485 bus are addressed to the
        control panel's channel, never ours, so waiting for one would mean never
        sending. Measured against real hardware.
        """
        try:
            await self._transport.write(frame)
        except ConnectionError as err:
            _LOGGER.warning("%s: send failed: %s", self.description, err)

    async def _read_loop(self) -> None:
        while not self._shutdown:
            try:
                chunk = await self._transport.read()
            except ConnectionError as err:
                _LOGGER.debug("%s: read error: %s", self.description, err)
                await self._transport.close()
                return
            if not chunk:
                _LOGGER.debug("%s: connection closed by peer", self.description)
                await self._transport.close()
                return

            changed = False
            for frame in self._reader.feed(chunk):
                self._last_frame_at = time.monotonic()
                if self._handle(frame):
                    changed = True
            if changed:
                self._notify()

    def _handle(self, frame: bytes) -> bool:
        """Fold one frame into the state. True if something worth reporting changed."""
        message = parse_frame(frame)

        if isinstance(message, StatusUpdate):
            previous = self._state.status
            self._state = self._state.with_status(message)
            self._check_configured()
            # Ignore the clock ticking so listeners are not woken every minute.
            return previous is None or _significant_change(previous, message)
        if isinstance(message, ControlConfiguration2):
            self._state = self._state.with_hardware(message)
            self._check_configured()
            return True
        if isinstance(message, ControlConfiguration):
            self._state = self._state.with_control_configuration(message)
            return True
        if isinstance(message, FilterCycles):
            self._state = self._state.with_filter_cycles(message)
            return True
        if isinstance(message, FaultLogEntry):
            # The whole log is re-read periodically, so most answers repeat what
            # we already had. Only report when the newest entry actually moves.
            previous_fault = self._state.latest_fault
            self._state = self._state.with_fault(message)
            current_fault = self._state.latest_fault
            return current_fault is not None and (
                previous_fault is None or previous_fault.raw != current_fault.raw
            )
        if isinstance(message, ModuleConfiguration):
            if message.mac_address:
                _LOGGER.debug("%s: MAC %s", self.description, message.mac_address)
                self._state = self._state.with_mac(message.mac_address)
                return True
            return False
        if isinstance(message, UnknownMessage):
            self.unknown_messages += 1
        return False

    def _check_configured(self) -> None:
        if not self._configured.is_set() and self._state.ready:
            self._configured.set()

    def _notify(self) -> None:
        for listener in list(self._listeners):
            try:
                listener()
            except Exception:
                _LOGGER.exception("listener raised")

    async def _monitor_loop(self) -> None:
        """Watch the frame clock and rebuild the connection when it stops."""
        attempt = 0
        was_available = True

        while not self._shutdown:
            await asyncio.sleep(MONITOR_INTERVAL)
            # `disconnect()` flips the flag from another task while we sleep, so
            # this is reachable even though mypy narrows it out of the loop test.
            if self._shutdown:
                return  # type: ignore[unreachable]

            silent_for = time.monotonic() - self._last_frame_at
            available = self.available
            if available != was_available:
                was_available = available
                self._notify()

            if self._transport.connected and silent_for < RECONNECT_AFTER:
                attempt = 0
                now = time.monotonic()
                if now - self._last_fault_request > FAULT_LOG_INTERVAL:
                    self._last_fault_request = now
                    await self.read_fault_log()
                continue

            if self._transport.connected:
                _LOGGER.info(
                    "%s: no data for %.0fs, reconnecting", self.description, silent_for
                )
                await self._transport.close()

            delay = min(
                INITIAL_BACKOFF * 2**attempt + uniform(0, INITIAL_BACKOFF), MAX_BACKOFF
            )
            attempt += 1
            await asyncio.sleep(delay)
            if self._shutdown:  # same as above: set concurrently by disconnect()
                return  # type: ignore[unreachable]

            try:
                await self._transport.connect()
            except ConnectionError as err:
                _LOGGER.debug("%s: reconnect failed: %s", self.description, err)
                continue

            _LOGGER.info("%s: reconnected", self.description)
            attempt = 0
            self._start_tasks()
            await self._request_configuration()
            self._start_fault_sweep()


def _significant_change(old: StatusUpdate, new: StatusUpdate) -> bool:
    """Whether two status frames differ in anything other than the clock."""
    return (
        old.pumps != new.pumps
        or old.lights != new.lights
        or old.aux != new.aux
        or old.blower != new.blower
        or old.mister != new.mister
        or old.circulation_pump != new.circulation_pump
        or old.heating != new.heating
        or old.heat_mode != new.heat_mode
        or old.temperature_range != new.temperature_range
        or old.temperature_unit != new.temperature_unit
        or old.current_temperature != new.current_temperature
        or old.target_temperature != new.target_temperature
        or old.filter_cycle_running != new.filter_cycle_running
        or old.notification != new.notification
        or old.hold != new.hold
        or old.priming != new.priming
        or old.twenty_four_hour_time != new.twenty_four_hour_time
    )
