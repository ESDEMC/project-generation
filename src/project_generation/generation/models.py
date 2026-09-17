import uuid
from dataclasses import dataclass, field
from typing import Any, Mapping

from project_generation.generation.rules import GroupRecord, StressPoint


@dataclass(frozen=True, kw_only=True)
class GeneratedPin:
    id: uuid.UUID
    designator: str
    name: str
    parameters: dict[str, Any] = field(default_factory=dict)

    def context(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "designator": self.designator,
            "name": self.name,
            "parameters": dict(self.parameters),
        }


@dataclass(frozen=True, kw_only=True)
class GeneratedPinMapEntry:
    pin: str
    location: str


@dataclass(frozen=True, kw_only=True)
class GeneratedGroup:
    id: uuid.UUID
    name: str
    group_type: str
    pin_ids: tuple[uuid.UUID, ...]
    bias_spec: Mapping[str, Any] = field(default_factory=dict)
    parameters: Mapping[str, Any] = field(default_factory=dict)
    generation_rule_id: str | None = None

    def context(self) -> dict[str, Any]:
        parameters = dict(self.parameters)
        return {
            "id": str(self.id),
            "name": self.name,
            "group_type": self.group_type,
            "bias_spec": dict(self.bias_spec),
            "parameters": parameters,
            **parameters,
        }

    def as_group_record(self) -> GroupRecord:
        return GroupRecord(
            name=self.name,
            group_type=self.group_type,
            parameters=self.parameters,
            bias=self.bias_spec,
        )


@dataclass(frozen=True, kw_only=True)
class GeneratedPowerDomain:
    name: str
    group_ids: tuple[uuid.UUID, ...]
    group_names: tuple[str, ...]
    assignment: str
    bias: Mapping[str, Any]
    timing: Mapping[str, Any] | None = None


@dataclass(frozen=True, kw_only=True)
class GeneratedPowerSequenceStep:
    index: int
    domain_name: str
    assignment: str
    group_ids: tuple[uuid.UUID, ...]
    group_names: tuple[str, ...]
    bias: Mapping[str, Any]
    delay: float
    after: str | None


def _power_domain_assignment_sort_key(domain: GeneratedPowerDomain) -> tuple[int, int, str]:
    assignment = domain.assignment.upper()
    if assignment.startswith("DC") and assignment[2:].isdigit():
        return 0, int(assignment[2:]), assignment
    if assignment == "GROUND":
        return 2, 0, assignment
    if assignment == "FLOATING":
        return 3, 0, assignment
    return 1, 0, assignment


@dataclass(frozen=True, kw_only=True)
class GeneratedDeviceState:
    id: uuid.UUID
    name: str
    extends: str | None
    power_domains: tuple[GeneratedPowerDomain, ...]
    power_on_sequence: tuple[GeneratedPowerSequenceStep, ...]
    power_off_sequence: tuple[GeneratedPowerSequenceStep, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "power_domains", tuple(sorted(self.power_domains, key=_power_domain_assignment_sort_key)))


@dataclass(frozen=True, kw_only=True)
class GeneratedTestGroup:
    group_id: uuid.UUID
    group_name: str
    stress_points: tuple[StressPoint, ...]
    # None means the whole generated group. SIGNAL plans use a one-pin subset so
    # each stress is applied to exactly one signal pin at a time.
    pin_ids: tuple[uuid.UUID, ...] | None = None




@dataclass(frozen=True, kw_only=True)
class GeneratedTemperatureControl:
    enabled: bool = True
    temperature: float = 25.0
    soak_time: float = 0.0
    factor: float = 1.0
    offset: float = 0.0
    start_tolerance: float = 10.0
    cool_temperature: float = 24.0
    timeout: float = 900.0


@dataclass(frozen=True, kw_only=True)
class GeneratedStressHardwareIssue:
    group_name: str
    stress_point_index: int
    stress: Mapping[str, Any]
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True, kw_only=True)
class GeneratedStressSupplyAssignment:
    resource: str
    strategy: str

@dataclass(frozen=True, kw_only=True)
class GeneratedTestPlan:
    id: uuid.UUID
    name: str
    test_type: str
    dimensions: Mapping[str, Any]
    device_state: str | None
    device_state_id: uuid.UUID | None
    test_groups: tuple[GeneratedTestGroup, ...]
    stress_supply: GeneratedStressSupplyAssignment | None = None
    hardware_issues: tuple[GeneratedStressHardwareIssue, ...] = ()
    temperature_control: GeneratedTemperatureControl | None = None
    generation_rule_id: str | None = None


@dataclass(frozen=True, kw_only=True)
class GeneratedProject:
    name: str
    metadata: Mapping[str, Any]
    dut_name: str | None
    pins: tuple[GeneratedPin, ...]
    groups: tuple[GeneratedGroup, ...]
    device_states: tuple[GeneratedDeviceState, ...]
    test_plans: tuple[GeneratedTestPlan, ...]
    pin_map: tuple[GeneratedPinMapEntry, ...] = ()


