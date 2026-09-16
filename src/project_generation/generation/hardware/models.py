from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Mapping, Sequence


class SourceMode(StrEnum):
    VOLTAGE = "VOLTAGE"
    CURRENT = "CURRENT"


@dataclass(frozen=True, kw_only=True)
class OperatingPoint:
    mode: SourceMode
    level: float
    compliance: float | None = None

    @classmethod
    def from_bias(cls, values: Mapping[str, Any]) -> "OperatingPoint":
        mode = SourceMode(str(values.get("mode") or "").upper())
        compliance = values.get("compliance_limit", values.get("compliance"))
        return cls(
            mode=mode,
            level=float(values["level"]),
            compliance=abs(float(compliance)) if compliance is not None else None,
        )


@dataclass(frozen=True, kw_only=True)
class DcEnvelope:
    max_voltage: float | None = None
    max_current: float | None = None
    min_voltage: float | None = None
    min_current: float | None = None

    @classmethod
    def from_mapping(cls, values: Mapping[str, Any]) -> "DcEnvelope":
        def number(name: str) -> float | None:
            value = values.get(name)
            return float(value) if value is not None else None

        return cls(
            max_voltage=number("max_voltage"),
            max_current=number("max_current"),
            min_voltage=number("min_voltage"),
            min_current=number("min_current"),
        )

    def rejection_reason(self, point: OperatingPoint) -> str | None:
        level = abs(point.level)
        level_axis = "voltage" if point.mode == SourceMode.VOLTAGE else "current"
        compliance_axis = "current" if point.mode == SourceMode.VOLTAGE else "voltage"
        maximum = self.max_voltage if level_axis == "voltage" else self.max_current
        minimum = self.min_voltage if level_axis == "voltage" else self.min_current
        compliance_maximum = self.max_current if compliance_axis == "current" else self.max_voltage

        if maximum is not None and level > maximum:
            return f"requested {level_axis} {level:g} exceeds DC maximum {maximum:g}"
        if minimum is not None and level != 0.0 and level < minimum:
            return f"requested {level_axis} {level:g} is below DC minimum {minimum:g}"
        if point.compliance is not None and compliance_maximum is not None and point.compliance > compliance_maximum:
            return (
                f"requested {compliance_axis} compliance {point.compliance:g} exceeds DC maximum "
                f"{compliance_maximum:g} at {level_axis} {level:g}"
            )
        return None


@dataclass(frozen=True, kw_only=True)
class PulseEnvelope:
    max_peak_voltage: float | None = None
    max_base_voltage: float | None = None
    max_peak_current: float | None = None
    max_base_current: float | None = None
    min_pulse_width: float | None = None
    max_pulse_width: float | None = None
    max_duty_cycle: float | None = None

    @classmethod
    def from_mapping(cls, values: Mapping[str, Any]) -> "PulseEnvelope":
        def number(name: str) -> float | None:
            value = values.get(name)
            return float(value) if value is not None else None

        return cls(
            max_peak_voltage=number("max_peak_voltage"),
            max_base_voltage=number("max_base_voltage"),
            max_peak_current=number("max_peak_current"),
            max_base_current=number("max_base_current"),
            min_pulse_width=number("min_pulse_width"),
            max_pulse_width=number("max_pulse_width"),
            max_duty_cycle=number("max_duty_cycle"),
        )

    def rejection_reason(self, stress: "BiasedPulseStress") -> str | None:
        peak_level = abs(stress.peak.level)
        peak_axis = "voltage" if stress.peak.mode == SourceMode.VOLTAGE else "current"
        compliance_axis = "current" if stress.peak.mode == SourceMode.VOLTAGE else "voltage"
        peak_maximum = self.max_peak_voltage if peak_axis == "voltage" else self.max_peak_current
        compliance_maximum = self.max_peak_current if compliance_axis == "current" else self.max_peak_voltage

        if peak_maximum is not None and peak_level > peak_maximum:
            return f"requested peak {peak_axis} {peak_level:g} exceeds PULSE maximum {peak_maximum:g}"
        if stress.peak.compliance is not None and compliance_maximum is not None and stress.peak.compliance > compliance_maximum:
            return (
                f"requested peak {compliance_axis} compliance {stress.peak.compliance:g} exceeds PULSE maximum "
                f"{compliance_maximum:g} at peak {peak_axis} {peak_level:g}"
            )
        if self.min_pulse_width is not None and stress.pulse_width < self.min_pulse_width:
            return (
                f"requested pulse width {stress.pulse_width:g} is below PULSE minimum "
                f"{self.min_pulse_width:g}"
            )
        if self.max_pulse_width is not None and stress.pulse_width > self.max_pulse_width:
            return (
                f"requested pulse width {stress.pulse_width:g} exceeds PULSE maximum "
                f"{self.max_pulse_width:g}"
            )
        if stress.duty_cycle is not None and self.max_duty_cycle is not None and stress.duty_cycle > self.max_duty_cycle:
            return (
                f"requested duty cycle {stress.duty_cycle:g} exceeds PULSE maximum "
                f"{self.max_duty_cycle:g}"
            )
        return None


@dataclass(frozen=True, kw_only=True)
class PowerSupplyCapabilities:
    dc_envelopes: tuple[DcEnvelope, ...] = ()
    pulse_envelopes: tuple[PulseEnvelope, ...] = ()

    @classmethod
    def from_mapping(cls, values: Mapping[str, Any]) -> "PowerSupplyCapabilities":
        dc = tuple(DcEnvelope.from_mapping(entry) for entry in values.get("DC") or [] if isinstance(entry, Mapping))
        pulse = tuple(
            PulseEnvelope.from_mapping(entry) for entry in values.get("PULSE") or [] if isinstance(entry, Mapping)
        )
        return cls(dc_envelopes=dc, pulse_envelopes=pulse)

    def dc_rejection_reason(self, point: OperatingPoint) -> str | None:
        if not self.dc_envelopes:
            return "hardware resource does not define a DC power envelope"
        reasons = [envelope.rejection_reason(point) for envelope in self.dc_envelopes]
        if any(reason is None for reason in reasons):
            return None
        if len(self.dc_envelopes) == 1:
            return reasons[0]
        level_axis = "voltage" if point.mode == SourceMode.VOLTAGE else "current"
        compliance_axis = "current" if point.mode == SourceMode.VOLTAGE else "voltage"
        requirement = f"{level_axis} {abs(point.level):g}"
        if point.compliance is not None:
            requirement += f" with {compliance_axis} compliance {point.compliance:g}"
        return f"no DC power envelope supports {requirement}"

    def pulse_rejection_reason(self, stress: "BiasedPulseStress") -> str | None:
        if not self.pulse_envelopes:
            return "hardware resource does not define a PULSE power envelope"
        reasons = [envelope.rejection_reason(stress) for envelope in self.pulse_envelopes]
        if any(reason is None for reason in reasons):
            return None
        if len(self.pulse_envelopes) == 1:
            return reasons[0]
        peak_axis = "voltage" if stress.peak.mode == SourceMode.VOLTAGE else "current"
        compliance_axis = "current" if stress.peak.mode == SourceMode.VOLTAGE else "voltage"
        requirement = f"peak {peak_axis} {abs(stress.peak.level):g}"
        if stress.peak.compliance is not None:
            requirement += f" with {compliance_axis} compliance {stress.peak.compliance:g}"
        requirement += f" and pulse width {stress.pulse_width:g}"
        return f"no PULSE power envelope supports {requirement}"


@dataclass(frozen=True, kw_only=True)
class HardwarePowerResource:
    assignment: str
    role: str
    connection_mode: str | None
    capabilities: PowerSupplyCapabilities


@dataclass(frozen=True, kw_only=True)
class BiasedPulseStress:
    bias: OperatingPoint
    peak: OperatingPoint
    pulse_width: float
    duty_cycle: float | None = None

    @classmethod
    def from_stress_point(cls, values: Mapping[str, Any]) -> "BiasedPulseStress":
        mode = SourceMode(str(values.get("source_mode") or "voltage").upper())
        compliance = values.get("compliance", values.get("compliance_limit"))
        compliance_value = abs(float(compliance)) if compliance is not None else None
        pulse_width = values.get("pulse_width", values.get("hold_time"))
        if pulse_width is None:
            raise ValueError("biased-pulse stress requires pulse_width")
        pulse_width = float(pulse_width)
        if pulse_width <= 0:
            raise ValueError("pulse_width must be greater than zero")
        duty_cycle = values.get("duty_cycle")
        duty_cycle_value = float(duty_cycle) if duty_cycle is not None else None
        if duty_cycle_value is not None and not 0 < duty_cycle_value <= 1:
            raise ValueError("duty_cycle must be greater than zero and no greater than one")
        return cls(
            bias=OperatingPoint(mode=mode, level=float(values.get("base", 0.0)), compliance=compliance_value),
            peak=OperatingPoint(mode=mode, level=float(values["peak"]), compliance=compliance_value),
            pulse_width=pulse_width,
            duty_cycle=duty_cycle_value,
        )


@dataclass(frozen=True, kw_only=True)
class StressSupplyCompatibility:
    accepted: bool
    reason: str | None = None


class SourceSwitchStressStrategy:
    name = "source_switch"

    def evaluate(self, resource: HardwarePowerResource, stress: BiasedPulseStress) -> StressSupplyCompatibility:
        if resource.role.upper() != "STRESS":
            return StressSupplyCompatibility(accepted=False, reason=f'role is "{resource.role.upper()}", not "STRESS"')
        if (resource.connection_mode or "").lower() != "switch":
            return StressSupplyCompatibility(
                accepted=False,
                reason=f'hardware connection mode is "{resource.connection_mode or "unknown"}", not "switch"',
            )

        reason = resource.capabilities.dc_rejection_reason(stress.bias)
        if reason is not None:
            return StressSupplyCompatibility(accepted=False, reason=f"pre/post bias: {reason}")

        # In the Source Switch strategy the separate bias leg provides the pre/post
        # base level. The pulse leg is therefore evaluated for the requested peak,
        # pulse width, and (when specified) duty cycle as one PULSE envelope.
        reason = resource.capabilities.pulse_rejection_reason(stress)
        if reason is not None:
            return StressSupplyCompatibility(accepted=False, reason=f"stress pulse: {reason}")
        return StressSupplyCompatibility(accepted=True)
