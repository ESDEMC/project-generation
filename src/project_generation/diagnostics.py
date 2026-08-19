from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Iterable, Mapping, Sequence


class DiagnosticSeverity(StrEnum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass(frozen=True, kw_only=True)
class GenerationDiagnostic:
    severity: DiagnosticSeverity
    code: str
    message: str
    location: str | None = None
    context: dict[str, Any] = field(default_factory=dict)

    def format(self) -> str:
        location = f" at {self.location}" if self.location else ""
        return f"{self.severity.value.upper()} {self.code}{location}: {self.message}"


class GenerationDiagnostics(list[GenerationDiagnostic]):
    def __init__(self, values: Iterable[GenerationDiagnostic] = ()) -> None:
        super().__init__(values)

    @property
    def has_errors(self) -> bool:
        return any(item.severity == DiagnosticSeverity.ERROR for item in self)


class ProjectGenerationError(ValueError):
    """Processing failure with a stable diagnostic payload."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "generation_error",
        location: str | None = None,
        owner: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        self.diagnostic = GenerationDiagnostic(
            severity=DiagnosticSeverity.ERROR,
            code=code,
            message=message,
            location=location,
            context={
                **({"owner": owner} if owner is not None else {}),
                **(context or {}),
            },
        )
        self.code = code
        self.location = location
        self.owner = owner
        self.context = self.diagnostic.context
        super().__init__(message)

    def format_diagnostic(self) -> str:
        return self.diagnostic.format()


@dataclass(frozen=True, kw_only=True)
class PowerResourceCandidateDiagnostic:
    resource: str
    accepted: bool
    reason: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "resource": self.resource,
            "accepted": self.accepted,
            **({"reason": self.reason} if self.reason is not None else {}),
        }


@dataclass(frozen=True, kw_only=True)
class PowerResourceResolutionIssue:
    state_name: str
    group_name: str
    bias: Mapping[str, Any]
    candidates: Sequence[PowerResourceCandidateDiagnostic]
    requested_resource: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "state_name": self.state_name,
            "group_name": self.group_name,
            "bias": dict(self.bias),
            "requested_resource": self.requested_resource,
            "candidates": [candidate.as_dict() for candidate in self.candidates],
        }


class PowerResourceResolutionError(ProjectGenerationError):
    """One or more device-state power requirements cannot be realized by configured hardware."""

    def __init__(self, issues: Sequence[PowerResourceResolutionIssue]) -> None:
        if not issues:
            raise ValueError("PowerResourceResolutionError requires at least one issue")

        self.issues = tuple(issues)
        first = self.issues[0]
        self.state_name = first.state_name
        self.group_name = first.group_name
        self.bias = dict(first.bias)
        self.candidates = tuple(first.candidates)
        self.requested_resource = first.requested_resource

        if len(self.issues) == 1 and first.requested_resource is not None:
            message = (
                f'Device state "{first.state_name}" cannot assign group "{first.group_name}" '
                f'to power resource "{first.requested_resource}"'
            )
            code = "hardware.power_resource_incompatible"
        elif len(self.issues) == 1:
            message = (
                f'Device state "{first.state_name}" cannot resolve a compatible power resource '
                f'for group "{first.group_name}"'
            )
            code = "hardware.power_resource_unresolved"
        else:
            message = f"Configured hardware cannot satisfy {len(self.issues)} device-state power requirements"
            code = "hardware.power_resources_unresolved"

        super().__init__(
            message,
            code=code,
            location=f"device_states.{first.state_name}",
            owner=first.state_name,
            context={"issues": [issue.as_dict() for issue in self.issues]},
        )

    def format_user_report(self) -> str:
        if len(self.issues) == 1:
            heading = f'Device state "{self.issues[0].state_name}" is not compatible with the configured hardware.'
        else:
            heading = f"Configured hardware cannot satisfy {len(self.issues)} device-state power requirements."

        lines = [heading]
        for index, issue in enumerate(self.issues):
            if index:
                lines.append("")
            lines.extend(["", f"Group: {issue.group_name}", f"Device state: {issue.state_name}", "Required bias:"])
            for key in ("mode", "level", "compliance_limit", "compliance"):
                if key in issue.bias:
                    lines.append(f"  {key}: {issue.bias[key]}")

            if issue.requested_resource is not None:
                lines.extend(["", f"Requested resource: {issue.requested_resource}"])

            lines.extend(["", "Power resources checked:"])
            if not issue.candidates:
                lines.append("  <none>")
            else:
                for candidate in issue.candidates:
                    status = (
                        "compatible"
                        if candidate.accepted
                        else f"rejected - {candidate.reason or 'not compatible'}"
                    )
                    lines.append(f"  {candidate.resource}: {status}")

        return "\n".join(lines)

@dataclass(frozen=True, kw_only=True)
class StressSupplyCandidateDiagnostic:
    resource: str
    strategy: str
    accepted: bool
    reason: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "resource": self.resource,
            "strategy": self.strategy,
            "accepted": self.accepted,
            **({"reason": self.reason} if self.reason is not None else {}),
        }


@dataclass(frozen=True, kw_only=True)
class StressSupplyResolutionIssue:
    plan_name: str
    group_name: str
    stress_point_index: int
    stress: Mapping[str, Any]
    candidates: Sequence[StressSupplyCandidateDiagnostic]

    def as_dict(self) -> dict[str, Any]:
        return {
            "plan_name": self.plan_name,
            "group_name": self.group_name,
            "stress_point_index": self.stress_point_index,
            "stress": dict(self.stress),
            "candidates": [candidate.as_dict() for candidate in self.candidates],
        }


class StressSupplyResolutionError(ProjectGenerationError):
    """One or more stress points cannot be realized by the configured stress hardware."""

    def __init__(self, issues: Sequence[StressSupplyResolutionIssue]) -> None:
        if not issues:
            raise ValueError("StressSupplyResolutionError requires at least one issue")
        self.issues = tuple(issues)
        first = self.issues[0]
        message = (
            f'Test plan "{first.plan_name}" cannot resolve compatible stress hardware'
            if len(self.issues) == 1
            else f"Configured hardware cannot satisfy {len(self.issues)} stress requirements"
        )
        super().__init__(
            message,
            code="hardware.stress_supply_unresolved",
            location=f"test_plans.{first.plan_name}",
            owner=first.plan_name,
            context={"issues": [issue.as_dict() for issue in self.issues]},
        )

    def format_user_report(self) -> str:
        lines = [
            f"Configured hardware cannot satisfy {len(self.issues)} stress requirement"
            + ("." if len(self.issues) == 1 else "s.")
        ]
        for issue in self.issues:
            lines.extend(
                [
                    "",
                    f"Test plan: {issue.plan_name}",
                    f"Group: {issue.group_name}",
                    f"Stress point: {issue.stress_point_index}",
                    "Required biased pulse:",
                ]
            )
            for key in ("source_mode", "base", "peak", "compliance", "compliance_limit", "pulse_width"):
                if key in issue.stress:
                    lines.append(f"  {key}: {issue.stress[key]}")
            lines.extend(["", "Stress resources checked:"])
            if not issue.candidates:
                lines.append("  <none>")
            for candidate in issue.candidates:
                status = "compatible" if candidate.accepted else f"rejected - {candidate.reason or 'not compatible'}"
                lines.append(f"  {candidate.resource} [{candidate.strategy}]: {status}")
        return "\n".join(lines)
