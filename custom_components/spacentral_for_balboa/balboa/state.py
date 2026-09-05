"""Aggregated view of a spa, assembled from the messages seen so far."""

from __future__ import annotations

from dataclasses import dataclass, replace

from .const import FAULT_AGE_UNKNOWN, MAX_AUX, MAX_LIGHTS, MAX_PUMPS
from .messages import (
    ControlConfiguration,
    ControlConfiguration2,
    FaultLogEntry,
    FilterCycles,
    StatusUpdate,
)

__all__ = ["SpaState", "manual_hardware"]


def manual_hardware(
    *,
    pump_count: int,
    light_count: int,
    aux_count: int,
    has_blower: bool,
    has_circulation_pump: bool,
    has_mister: bool,
) -> ControlConfiguration2:
    """Build a hardware descriptor from user-entered counts.

    For a controller that never answers the real request (observed on
    SIBP2P/Colossus boards), entered once through the config flow and
    editable afterwards through the options flow.

    Every configured pump is single-speed, whatever the real pump's speed
    count: a 2-speed pump reports a *current* speed of 0, 1 or 2, but this
    guess has no way to know which, and guessing wrong is not something that
    merely looks off -- `SpaClient._pump_reached` compares against the
    guessed count, so a pump guessed at 2 speeds when it only has one would
    have `set_pump` retry a "medium" request the hardware can never report
    back, physically toggling the real pump up to `TOGGLE_LIMIT` times before
    giving up. Single-speed is the one guess that can only ever ask for
    on/off, which every pump supports.
    """
    return ControlConfiguration2(
        channel=0,
        raw=b"",
        pumps=tuple(1 if i < pump_count else 0 for i in range(MAX_PUMPS)),
        lights=tuple(i < light_count for i in range(MAX_LIGHTS)),
        aux=tuple(i < aux_count for i in range(MAX_AUX)),
        blower_speeds=1 if has_blower else 0,
        circulation_pump=has_circulation_pump,
        mister=has_mister,
    )


@dataclass(frozen=True, slots=True)
class SpaState:
    """Immutable snapshot. Entities read from it, never write to it."""

    status: StatusUpdate | None = None
    control_configuration: ControlConfiguration | None = None
    hardware: ControlConfiguration2 | None = None
    filter_cycles: FilterCycles | None = None
    fault_log: tuple[FaultLogEntry, ...] = ()
    mac_address: str | None = None

    @property
    def ready(self) -> bool:
        """Whether enough is known to create entities.

        Deliberately does *not* require the configuration response carrying the
        MAC: setups without a Balboa Wi-Fi module never answer that request.
        Requiring it is exactly what makes other libraries fail on an RS-485
        gateway.
        """
        return self.status is not None and self.hardware is not None

    @property
    def model(self) -> str:
        if self.control_configuration is None:
            return "Balboa Spa"
        return self.control_configuration.model or "Balboa Spa"

    @property
    def software_version(self) -> str | None:
        if self.control_configuration is None:
            return None
        return self.control_configuration.version

    # ── Hardware capabilities ────────────────────────────────────────────────

    def pump_speeds(self, index: int) -> int:
        """Number of speeds pump `index` has; 0 means it is not fitted."""
        if self.hardware is None or not 0 <= index < MAX_PUMPS:
            return 0
        return self.hardware.pumps[index]

    @property
    def has_circulation_pump(self) -> bool:
        return self.hardware is not None and self.hardware.circulation_pump

    @property
    def blower_speeds(self) -> int:
        return self.hardware.blower_speeds if self.hardware else 0

    def has_light(self, index: int) -> bool:
        if self.hardware is None or not 0 <= index < MAX_LIGHTS:
            return False
        return self.hardware.lights[index]

    def has_aux(self, index: int) -> bool:
        if self.hardware is None or not 0 <= index < MAX_AUX:
            return False
        return self.hardware.aux[index]

    @property
    def has_mister(self) -> bool:
        return self.hardware is not None and self.hardware.mister

    # ── Current values ───────────────────────────────────────────────────────

    def pump_state(self, index: int) -> int:
        """Current pump speed, 0 when off.

        Careful: a *single-speed* pump reports 2 when running, not 1 -- measured
        on real hardware. Use `is_pump_on` for a boolean, and only compare this
        against `pump_speeds` for genuinely multi-speed pumps.
        """
        if self.status is None or not 0 <= index < MAX_PUMPS:
            return 0
        return self.status.pumps[index]

    def is_pump_on(self, index: int) -> bool:
        return self.pump_state(index) != 0

    def is_light_on(self, index: int) -> bool:
        if self.status is None or not 0 <= index < MAX_LIGHTS:
            return False
        return self.status.lights[index]

    def is_aux_on(self, index: int) -> bool:
        if self.status is None or not 0 <= index < MAX_AUX:
            return False
        return self.status.aux[index]

    # ── Updating ─────────────────────────────────────────────────────────────

    def with_status(self, status: StatusUpdate) -> SpaState:
        return replace(self, status=status)

    def with_control_configuration(self, config: ControlConfiguration) -> SpaState:
        return replace(self, control_configuration=config)

    def with_hardware(self, hardware: ControlConfiguration2) -> SpaState:
        return replace(self, hardware=hardware)

    def with_filter_cycles(self, cycles: FilterCycles) -> SpaState:
        return replace(self, filter_cycles=cycles)

    @property
    def latest_fault(self) -> FaultLogEntry | None:
        """The most recent entry of the fault log.

        Chosen by the smallest `days_ago` rather than by position. Sweeps of two
        controllers both showed the age falling as the index rises, so the
        newest entry sits at the end -- but answers get lost on a busy bus, and
        the age field says what it means whether or not the last slot arrived.
        """
        if not self.fault_log:
            return None
        dated = [f for f in self.fault_log if f.days_ago != FAULT_AGE_UNKNOWN]
        if dated:
            return min(dated, key=lambda f: f.days_ago)
        return max(self.fault_log, key=lambda f: f.entry)

    def with_fault(self, fault: FaultLogEntry) -> SpaState:
        """Add or replace one entry, keeping the log ordered by index."""
        others = [f for f in self.fault_log if f.entry != fault.entry]
        return replace(
            self, fault_log=tuple(sorted([*others, fault], key=lambda f: f.entry))
        )

    def with_mac(self, mac: str | None) -> SpaState:
        return replace(self, mac_address=mac) if mac else self
