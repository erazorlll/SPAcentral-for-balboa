"""Typed representation of the messages a Balboa controller exchanges.

Parsing never raises on unexpected input: anything unrecognised or too short
becomes an `UnknownMessage`, which the client counts and otherwise ignores.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from .const import (
    CELSIUS_DIVISOR,
    CLIENT_CHANNEL,
    CONTROL_CONFIG_REQUEST_PAYLOADS,
    FAULT_CODES,
    FAULT_LOG_SELECTOR,
    TEMPERATURE_UNKNOWN,
    HeatMode,
    MessageType,
    Notification,
    TemperatureRange,
    TemperatureUnit,
    ToggleItem,
)
from .framing import build_frame

__all__ = [
    "ControlConfiguration",
    "ControlConfiguration2",
    "FaultLogEntry",
    "FilterCycles",
    "Message",
    "ModuleConfiguration",
    "SetTemperatureMessage",
    "SetTimeMessage",
    "StatusUpdate",
    "ToggleItemMessage",
    "UnknownMessage",
    "parse_frame",
    "request_configuration",
    "request_control_configuration",
    "request_fault_log",
    "set_filter_cycles",
    "set_temperature",
    "set_time",
    "toggle",
]


@dataclass(frozen=True, slots=True)
class Message:
    """Base for every decoded message."""

    channel: int
    raw: bytes


@dataclass(frozen=True, slots=True)
class UnknownMessage(Message):
    """A well-formed frame whose type we do not model."""

    message_type: bytes


@dataclass(frozen=True, slots=True)
class ReadyMessage(Message):
    """RS-485 send token. Addressed to one channel, usually not ours."""


@dataclass(frozen=True, slots=True)
class NothingToSendMessage(Message):
    """A polled participant answering that it has nothing to transmit."""


@dataclass(frozen=True, slots=True)
class NewClientClearToSendMessage(Message):
    """Invitation for unregistered clients to request a channel."""


@dataclass(frozen=True, slots=True)
class ErrorMessage(Message):
    """The controller reporting a fault."""

    code: int


@dataclass(frozen=True, slots=True)
class ToggleItemMessage(Message):
    """A toggle command seen on the bus.

    Usually sent by the control panel rather than by us -- the RS-485 tap sees
    the whole bus, so pressing a button on the spa shows up here.
    """

    item: ToggleItem | int


@dataclass(frozen=True, slots=True)
class SetTemperatureMessage(Message):
    """A target temperature command seen on the bus.

    The raw value is in the unit the controller currently uses: halves for
    Celsius, whole degrees for Fahrenheit.
    """

    raw_value: int


@dataclass(frozen=True, slots=True)
class SetTimeMessage(Message):
    """A clock-setting command seen on the bus."""

    hour: int
    minute: int
    twenty_four_hour: bool


@dataclass(frozen=True, slots=True)
class ModuleConfiguration(Message):
    """Configuration response -- the only message carrying a MAC address.

    Many setups never answer the request for it; an RS-485 tap without a Balboa
    Wi-Fi module is one of them.
    """

    mac_address: str | None


@dataclass(frozen=True, slots=True)
class ControlConfiguration(Message):
    """Model name and software version."""

    model: str
    software_id: str
    version: str


@dataclass(frozen=True, slots=True)
class ControlConfiguration2(Message):
    """Which hardware this spa actually has.

    `pumps[i]` is the number of *speeds*: 0 absent, 1 single-speed, 2 two-speed.
    Do not confuse it with the current speed reported in the status update.
    """

    pumps: tuple[int, ...]
    lights: tuple[bool, ...]
    aux: tuple[bool, ...]
    blower_speeds: int
    circulation_pump: bool
    mister: bool

    @property
    def pump_count(self) -> int:
        return sum(1 for speeds in self.pumps if speeds)


@dataclass(frozen=True, slots=True)
class FilterCycles(Message):
    """Start time and duration of both filter cycles."""

    cycle_1_start_hour: int
    cycle_1_start_minute: int
    cycle_1_duration_hours: int
    cycle_1_duration_minutes: int
    cycle_2_enabled: bool
    cycle_2_start_hour: int
    cycle_2_start_minute: int
    cycle_2_duration_hours: int
    cycle_2_duration_minutes: int

    @property
    def cycle_1_duration(self) -> int:
        """Length of the first cycle in minutes."""
        return self.cycle_1_duration_hours * 60 + self.cycle_1_duration_minutes

    @property
    def cycle_2_duration(self) -> int:
        """Length of the second cycle in minutes."""
        return self.cycle_2_duration_hours * 60 + self.cycle_2_duration_minutes

    def start(self, cycle: int) -> tuple[int, int]:
        """Start hour and minute of cycle 1 or 2."""
        if cycle == 1:
            return self.cycle_1_start_hour, self.cycle_1_start_minute
        return self.cycle_2_start_hour, self.cycle_2_start_minute

    def duration(self, cycle: int) -> int:
        """Length of cycle 1 or 2 in minutes."""
        return self.cycle_1_duration if cycle == 1 else self.cycle_2_duration

    def with_start(self, cycle: int, hour: int, minute: int) -> FilterCycles:
        """A copy with one cycle's start time changed."""
        if cycle == 1:
            return replace(self, cycle_1_start_hour=hour, cycle_1_start_minute=minute)
        return replace(self, cycle_2_start_hour=hour, cycle_2_start_minute=minute)

    def with_duration(self, cycle: int, minutes: int) -> FilterCycles:
        """A copy with one cycle's length changed.

        The controller stores hours and minutes separately, so the value is
        split here rather than in every caller.
        """
        hours, mins = divmod(max(0, minutes), 60)
        if cycle == 1:
            return replace(
                self, cycle_1_duration_hours=hours, cycle_1_duration_minutes=mins
            )
        return replace(self, cycle_2_duration_hours=hours, cycle_2_duration_minutes=mins)


@dataclass(frozen=True, slots=True)
class FaultLogEntry(Message):
    """One entry of the controller's rolling fault log.

    Temperatures are kept as the controller sent them. The entry carries no
    scale of its own, so converting needs the unit the spa is currently using --
    hence `temperatures()` rather than plain attributes. The decoding was
    confirmed by a captured entry whose values matched the spa's live target
    and water temperature exactly.
    """

    #: A lifetime counter, not the number of stored entries: a controller with
    #: a 24-entry log reported 152 here. Kept under a name that does not claim
    #: more than was measured.
    counter: int
    entry: int
    code: int
    #: 255 appears to mean "longer ago than this counts", but that is not
    #: something the captures can confirm, so it is passed through unchanged.
    days_ago: int
    hour: int
    minute: int
    flags: int
    target_temperature_raw: int
    sensor_a_temperature_raw: int
    sensor_b_temperature_raw: int

    @property
    def name(self) -> str:
        """A stable key for this fault, or the raw code if it is unknown."""
        return FAULT_CODES.get(self.code, f"code_{self.code}")

    def temperatures(
        self, unit: TemperatureUnit
    ) -> tuple[float | None, float | None, float | None]:
        """Target, sensor A and sensor B, scaled to the spa's unit."""
        divisor = CELSIUS_DIVISOR if unit is TemperatureUnit.CELSIUS else 1.0

        def scale(value: int) -> float | None:
            return None if value == 0 else value / divisor

        return (
            scale(self.target_temperature_raw),
            scale(self.sensor_a_temperature_raw),
            scale(self.sensor_b_temperature_raw),
        )


@dataclass(frozen=True, slots=True)
class StatusUpdate(Message):
    """The once-per-300ms broadcast carrying everything that changes."""

    hold: bool
    priming: bool
    heat_mode: HeatMode
    notification: Notification
    temperature_unit: TemperatureUnit
    twenty_four_hour_time: bool
    filter_cycle_running: tuple[bool, bool]
    heating: bool
    temperature_range: TemperatureRange
    pumps: tuple[int, ...]
    circulation_pump: bool
    blower: int
    lights: tuple[bool, ...]
    mister: bool
    aux: tuple[bool, ...]
    hour: int
    minute: int
    current_temperature: float | None
    target_temperature: float | None


# ── Parsing ───────────────────────────────────────────────────────────────────


def _mac_from(data: bytes) -> str | None:
    """Extract the MAC from a configuration response payload."""
    if len(data) < 9:
        return None
    mac = data[3:9]
    if not any(mac):
        return None
    return ":".join(f"{byte:02x}" for byte in mac)


def _parse_status(channel: int, raw: bytes, data: bytes) -> Message:
    if len(data) < 21:
        return UnknownMessage(channel, raw, MessageType.STATUS_UPDATE.value)

    unit = TemperatureUnit.CELSIUS if data[9] & 0x01 else TemperatureUnit.FAHRENHEIT
    divisor = CELSIUS_DIVISOR if unit is TemperatureUnit.CELSIUS else 1.0

    current: float | None = None
    if data[2] != TEMPERATURE_UNKNOWN:
        current = data[2] / divisor
    target: float | None = data[20] / divisor if data[20] else None

    try:
        heat_mode = HeatMode(data[5] & 0x03)
    except ValueError:
        heat_mode = HeatMode.READY

    notification = Notification.NONE
    if data[1] == 0x03:
        try:
            notification = Notification(data[6])
        except ValueError:
            notification = Notification.NONE

    return StatusUpdate(
        channel=channel,
        raw=raw,
        hold=bool(data[0] & 0x05),
        priming=data[1] == 0x01,
        heat_mode=heat_mode,
        notification=notification,
        temperature_unit=unit,
        twenty_four_hour_time=bool(data[9] & 0x02),
        filter_cycle_running=(bool(data[9] & 0x04), bool(data[9] & 0x08)),
        heating=bool(data[10] & 0x30),
        temperature_range=(
            TemperatureRange.HIGH if data[10] & 0x04 else TemperatureRange.LOW
        ),
        pumps=(
            data[11] & 0x03,
            (data[11] >> 2) & 0x03,
            (data[11] >> 4) & 0x03,
            (data[11] >> 6) & 0x03,
            data[12] & 0x03,
            (data[12] >> 2) & 0x03,
        ),
        circulation_pump=bool(data[13] & 0x02),
        blower=(data[13] >> 2) & 0x03,
        lights=(bool(data[14] & 0x03), bool((data[14] >> 2) & 0x03)),
        mister=bool(data[15] & 0x01),
        aux=(bool(data[15] & 0x08), bool(data[15] & 0x10)),
        hour=data[3],
        minute=data[4],
        current_temperature=current,
        target_temperature=target,
    )


def _parse_fault_log(channel: int, raw: bytes, data: bytes) -> Message:
    if len(data) < 10:
        return UnknownMessage(channel, raw, MessageType.FAULT_LOG.value)

    return FaultLogEntry(
        channel=channel,
        raw=raw,
        counter=data[0],
        entry=data[1],
        code=data[2],
        days_ago=data[3],
        hour=data[4],
        minute=data[5],
        flags=data[6],
        target_temperature_raw=data[7],
        sensor_a_temperature_raw=data[8],
        sensor_b_temperature_raw=data[9],
    )


def _parse_control_configuration(channel: int, raw: bytes, data: bytes) -> Message:
    if len(data) < 13:
        return UnknownMessage(channel, raw, MessageType.CONTROL_CONFIGURATION.value)
    model = data[4:12].decode("ascii", errors="replace").strip()
    return ControlConfiguration(
        channel=channel,
        raw=raw,
        model=model,
        software_id=f"{data[0]:02x}{data[1]:02x}",
        version=f"{data[2]}.{data[3]}",
    )


def _parse_control_configuration_2(channel: int, raw: bytes, data: bytes) -> Message:
    if len(data) < 5:
        return UnknownMessage(channel, raw, MessageType.CONTROL_CONFIGURATION_2.value)
    return ControlConfiguration2(
        channel=channel,
        raw=raw,
        pumps=(
            data[0] & 0x03,
            (data[0] >> 2) & 0x03,
            (data[0] >> 4) & 0x03,
            (data[0] >> 6) & 0x03,
            data[1] & 0x03,
            (data[1] >> 6) & 0x03,
        ),
        lights=(bool(data[2] & 0x03), bool((data[2] >> 6) & 0x03)),
        blower_speeds=data[3] & 0x03,
        circulation_pump=bool((data[3] >> 6) & 0x03),
        mister=bool(data[4] & 0x30),
        aux=(bool(data[4] & 0x01), bool(data[4] & 0x02)),
    )


def _parse_filter_cycles(channel: int, raw: bytes, data: bytes) -> Message:
    if len(data) < 8:
        return UnknownMessage(channel, raw, MessageType.FILTER_CYCLES.value)
    return FilterCycles(
        channel=channel,
        raw=raw,
        cycle_1_start_hour=data[0],
        cycle_1_start_minute=data[1],
        cycle_1_duration_hours=data[2],
        cycle_1_duration_minutes=data[3],
        cycle_2_enabled=bool(data[4] & 0x80),
        cycle_2_start_hour=data[4] & 0x7F,
        cycle_2_start_minute=data[5],
        cycle_2_duration_hours=data[6],
        cycle_2_duration_minutes=data[7],
    )


_SIMPLE: dict[bytes, type[Message]] = {
    MessageType.READY.value: ReadyMessage,
    MessageType.NOTHING_TO_SEND.value: NothingToSendMessage,
    MessageType.NEW_CLIENT_CLEAR_TO_SEND.value: NewClientClearToSendMessage,
}


def parse_frame(frame: bytes) -> Message:
    """Decode one validated frame. Never raises."""
    if len(frame) < 7:
        return UnknownMessage(0, frame, b"")

    channel = frame[2]
    message_type = frame[3:5]
    data = frame[5:-2]

    if (simple := _SIMPLE.get(message_type)) is not None:
        return simple(channel, frame)
    if message_type == MessageType.STATUS_UPDATE.value:
        return _parse_status(channel, frame, data)
    if message_type == MessageType.CONTROL_CONFIGURATION.value:
        return _parse_control_configuration(channel, frame, data)
    if message_type == MessageType.CONTROL_CONFIGURATION_2.value:
        return _parse_control_configuration_2(channel, frame, data)
    if message_type == MessageType.FILTER_CYCLES.value:
        return _parse_filter_cycles(channel, frame, data)
    if message_type == MessageType.FAULT_LOG.value:
        return _parse_fault_log(channel, frame, data)
    if message_type == MessageType.CONFIGURATION.value:
        return ModuleConfiguration(channel, frame, _mac_from(data))
    if message_type == MessageType.ERROR.value:
        return ErrorMessage(channel, frame, data[0] if data else 0)
    if message_type == MessageType.TOGGLE_ITEM.value and data:
        try:
            item: ToggleItem | int = ToggleItem(data[0])
        except ValueError:
            item = data[0]
        return ToggleItemMessage(channel, frame, item)
    if message_type == MessageType.SET_TEMPERATURE.value and data:
        return SetTemperatureMessage(channel, frame, data[0])
    if message_type == MessageType.SET_TIME.value and len(data) >= 2:
        return SetTimeMessage(
            channel, frame, data[0] & 0x7F, data[1], bool(data[0] & 0x80)
        )
    return UnknownMessage(channel, frame, message_type)


# ── Outgoing messages ─────────────────────────────────────────────────────────


def request_configuration() -> bytes:
    """Ask for the configuration response (the one carrying the MAC)."""
    return build_frame(CLIENT_CHANNEL, MessageType.CONFIGURATION_REQUEST.value)


def request_control_configuration(kind: int) -> bytes:
    """Ask for control configuration 1, 2 or the filter cycles (3)."""
    payload = CONTROL_CONFIG_REQUEST_PAYLOADS.get(kind)
    if payload is None:
        raise ValueError(f"unknown control configuration request: {kind}")
    return build_frame(
        CLIENT_CHANNEL, MessageType.CONTROL_CONFIGURATION_REQUEST.value, payload
    )


def request_fault_log(entry: int = 0) -> bytes:
    """Ask for one fault log entry.

    The entry number goes in the second payload byte. The first is a selector
    shared with the other configuration requests -- putting an index there
    would return the filter cycles instead.
    """
    if not 0 <= entry <= 0xFF:
        raise ValueError(f"fault log entry out of range: {entry}")
    return build_frame(
        CLIENT_CHANNEL,
        MessageType.CONTROL_CONFIGURATION_REQUEST.value,
        bytes([FAULT_LOG_SELECTOR, entry, 0x00]),
    )


def toggle(item: ToggleItem) -> bytes:
    """Cycle an item to its next state.

    The protocol has no "set to state X" command for pumps, lights or modes --
    everything is a toggle that advances one step.
    """
    return build_frame(CLIENT_CHANNEL, MessageType.TOGGLE_ITEM.value, bytes([item, 0x00]))


def set_temperature(temperature: float, unit: TemperatureUnit) -> bytes:
    """Set the target temperature, in the unit the spa is currently using."""
    divisor = CELSIUS_DIVISOR if unit is TemperatureUnit.CELSIUS else 1.0
    raw = round(temperature * divisor)
    if not 0 <= raw <= 0xFF:
        raise ValueError(f"target temperature out of range: {temperature}")
    return build_frame(CLIENT_CHANNEL, MessageType.SET_TEMPERATURE.value, bytes([raw]))


def set_time(hour: int, minute: int, *, twenty_four_hour: bool) -> bytes:
    """Set the controller's clock."""
    if not 0 <= hour < 24 or not 0 <= minute < 60:
        raise ValueError(f"invalid time: {hour}:{minute}")
    return build_frame(
        CLIENT_CHANNEL,
        MessageType.SET_TIME.value,
        bytes([(0x80 if twenty_four_hour else 0x00) | hour, minute]),
    )


def set_filter_cycles(cycles: FilterCycles) -> bytes:
    """Write both filter cycles back to the controller.

    The same message type the controller answers with; the enable flag for the
    second cycle rides in the high bit of its start hour.
    """
    start_2 = cycles.cycle_2_start_hour & 0x7F
    if cycles.cycle_2_enabled:
        start_2 |= 0x80

    payload = bytes(
        [
            cycles.cycle_1_start_hour,
            cycles.cycle_1_start_minute,
            cycles.cycle_1_duration_hours,
            cycles.cycle_1_duration_minutes,
            start_2,
            cycles.cycle_2_start_minute,
            cycles.cycle_2_duration_hours,
            cycles.cycle_2_duration_minutes,
        ]
    )
    return build_frame(CLIENT_CHANNEL, MessageType.FILTER_CYCLES.value, payload)


def set_temperature_unit(unit: TemperatureUnit) -> bytes:
    """Switch the controller between Celsius and Fahrenheit."""
    return build_frame(
        CLIENT_CHANNEL,
        MessageType.SET_TEMPERATURE_SCALE.value,
        bytes([0x01, 0x01 if unit is TemperatureUnit.CELSIUS else 0x00]),
    )
