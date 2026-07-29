"""Aggregated view of a spa, assembled from the messages seen so far."""

from __future__ import annotations

from dataclasses import dataclass, replace

from .const import MAX_AUX, MAX_LIGHTS, MAX_PUMPS
from .messages import (
    ControlConfiguration,
    ControlConfiguration2,
    FilterCycles,
    StatusUpdate,
)

__all__ = ["SpaState"]


@dataclass(frozen=True, slots=True)
class SpaState:
    """Immutable snapshot. Entities read from it, never write to it."""

    status: StatusUpdate | None = None
    control_configuration: ControlConfiguration | None = None
    hardware: ControlConfiguration2 | None = None
    filter_cycles: FilterCycles | None = None
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

    def with_mac(self, mac: str | None) -> SpaState:
        return replace(self, mac_address=mac) if mac else self
