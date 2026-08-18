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
class GeneratedGroup:
    id: uuid.UUID
    name: str
    group_type: str
    pin_ids: tuple[uuid.UUID, ...]
    parameters: Mapping[str, Any] = field(default_factory=dict)
    generation_rule_id: str | None = None

    def context(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "name": self.name,
            "group_type": self.group_type,
            "parameters": dict(self.parameters),
        }

    def as_group_record(self) -> GroupRecord:
        return GroupRecord(name=self.name, group_type=self.group_type, parameters=self.parameters)


@dataclass(frozen=True, kw_only=True)
class GeneratedPowerDomain:
    name: str
    group_ids: tuple[uuid.UUID, ...]
    group_names: tuple[str, ...]
    assignment: str
    bias: Mapping[str, Any]
    timing: Mapping[str, Any] | None = None


@dataclass(frozen=True, kw_only=True)
class GeneratedGroupState:
    group_id: uuid.UUID
    group_name: str
    values: Mapping[str, Any]


@dataclass(frozen=True, kw_only=True)
class GeneratedPowerAssignment:
    group_id: uuid.UUID
    group_name: str
    assignment: str
    bias: Mapping[str, Any]
    source: str


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


@dataclass(frozen=True, kw_only=True)
class GeneratedDeviceState:
    id: uuid.UUID
    name: str
    extends: str | None
    allocation: Mapping[str, Any] | None
    power_domains: tuple[GeneratedPowerDomain, ...]
    group_states: tuple[GeneratedGroupState, ...]
    power_assignments: tuple[GeneratedPowerAssignment, ...]
    power_on_sequence: tuple[GeneratedPowerSequenceStep, ...]
    power_off_sequence: tuple[GeneratedPowerSequenceStep, ...]


@dataclass(frozen=True, kw_only=True)
class GeneratedTestGroup:
    group_id: uuid.UUID
    group_name: str
    stress_points: tuple[StressPoint, ...]


@dataclass(frozen=True, kw_only=True)
class GeneratedTestPlan:
    id: uuid.UUID
    name: str
    test_type: str
    dimensions: Mapping[str, Any]
    device_state: str | None
    device_state_id: uuid.UUID | None
    test_groups: tuple[GeneratedTestGroup, ...]
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


