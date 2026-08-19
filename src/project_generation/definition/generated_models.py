from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class GeneratedDefinitionModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class ProjectMetadata(GeneratedDefinitionModel):
    name: str | None = None
    source: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class InlineSource(GeneratedDefinitionModel):
    type: Literal["inline"] = "inline"
    records: list[dict[str, Any]]


class SourceFieldMapping(GeneratedDefinitionModel):
    from_: str = Field(alias="from")
    mapping: str | None = None
    formatter: str | None = None


class JsonSource(GeneratedDefinitionModel):
    type: Literal["json"] = "json"
    path: str
    select: str | None = None
    mapping: dict[str, str | SourceFieldMapping] = Field(default_factory=dict)


class CsvSource(GeneratedDefinitionModel):
    type: Literal["csv"] = "csv"
    path: str
    mapping: dict[str, str | SourceFieldMapping] = Field(default_factory=dict)


class ExcelSource(GeneratedDefinitionModel):
    type: Literal["excel"] = "excel"
    path: str
    sheet: str | int | None = None
    mapping: dict[str, str | SourceFieldMapping] = Field(default_factory=dict)


class NamedSourceReference(GeneratedDefinitionModel):
    source: str


class InlineSourceReference(GeneratedDefinitionModel):
    source: InlineSource | JsonSource | CsvSource | ExcelSource


class DutDefinition(GeneratedDefinitionModel):
    name: str
    pins: NamedSourceReference | InlineSourceReference


class ExplicitGroupDefinition(GeneratedDefinitionModel):
    name: str
    group_type: str
    pins: list[str]
    parameters: dict[str, Any] = Field(default_factory=dict)


class SelectionDefinition(GeneratedDefinitionModel):
    where: dict[str, Any] = Field(default_factory=dict)


class ValueDefinition(GeneratedDefinitionModel):
    from_: str | None = Field(default=None, alias="from")
    value: Any = None
    aggregate: str | None = None
    mapping: str | None = None
    formatter: str | None = None
    cast: Literal["float", "int", "str", "bool"] | None = None
    when: dict[str, Any] | None = None


class NameFieldDefinition(GeneratedDefinitionModel):
    source: str
    mapping: str | None = None
    formatter: str | None = None
    when: dict[str, Any] | None = None


class NameTemplateDefinition(GeneratedDefinitionModel):
    template: str
    fields: dict[str, NameFieldDefinition] = Field(default_factory=dict)


class GroupGenerationRule(GeneratedDefinitionModel):
    id: str
    select: SelectionDefinition = Field(default_factory=SelectionDefinition)
    group_by: list[str]
    set: dict[str, Any] = Field(default_factory=dict)
    name: NameTemplateDefinition


class GroupsDefinition(GeneratedDefinitionModel):
    external: bool = False
    explicit: list[ExplicitGroupDefinition] = Field(default_factory=list)
    generation: list[GroupGenerationRule] = Field(default_factory=list)


class FormatterDefinition(GeneratedDefinitionModel):
    type: str
    separator: str | None = None
    decimal_places: int | None = None


class HardwareDefinition(GeneratedDefinitionModel):
    source: str


class PowerResourceDefinition(GeneratedDefinitionModel):
    role: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)


class BiasDefinition(GeneratedDefinitionModel):
    mode: str
    level: Any = None


class PowerSequenceTimingDefinition(GeneratedDefinitionModel):
    delay: float = 0.0
    after: str | None = None


class TimingDefinition(GeneratedDefinitionModel):
    power_on: PowerSequenceTimingDefinition | None = None
    power_off: PowerSequenceTimingDefinition | None = None


class PowerDomainDefinition(GeneratedDefinitionModel):
    name: str
    groups: list[str]
    assignment: str
    bias: BiasDefinition
    timing: TimingDefinition | None = None


class AllocationDefinition(GeneratedDefinitionModel):
    mode: Literal["direct", "automatic", "hybrid"]
    strategy: str | None = None
    reserve: list[str] = Field(default_factory=list)
    ganging_policy: str | None = None


class DeviceStateRuleDefinition(GeneratedDefinitionModel):
    when: dict[str, Any]
    set: dict[str, Any]


class DeviceStateDefinition(GeneratedDefinitionModel):
    extends: str | None = None
    power_domains: list[PowerDomainDefinition] = Field(default_factory=list)
    allocation: AllocationDefinition | None = None
    rules: list[DeviceStateRuleDefinition] = Field(default_factory=list)


class EachPartitionDefinition(GeneratedDefinitionModel):
    mode: Literal["each"]


class AllPartitionDefinition(GeneratedDefinitionModel):
    mode: Literal["all"]


class GroupByPartitionDefinition(GeneratedDefinitionModel):
    mode: Literal["group_by"]
    fields: list[str]


class TestGroupsDefinition(GeneratedDefinitionModel):
    select: SelectionDefinition = Field(default_factory=SelectionDefinition)
    partition: EachPartitionDefinition | AllPartitionDefinition | GroupByPartitionDefinition


class DimensionValueDefinition(GeneratedDefinitionModel):
    value: Any
    set: dict[str, Any] = Field(default_factory=dict)


class DimensionDefinition(GeneratedDefinitionModel):
    name: str
    values: list[DimensionValueDefinition | str | int | float | bool | None]


class OverrideScope(str, Enum):
    plan = "plan"
    group = "group"


class OverrideDefinition(GeneratedDefinitionModel):
    scope: OverrideScope = OverrideScope.plan
    when: dict[str, Any]
    set: dict[str, Any] = Field(default_factory=dict)
    exclude: bool = False


class TestPlanRuleDefinition(GeneratedDefinitionModel):
    id: str
    groups: TestGroupsDefinition
    dimensions: list[DimensionDefinition] = Field(default_factory=list)
    template: dict[str, Any]
    overrides: list[OverrideDefinition] = Field(default_factory=list)


class TestPlanGenerationDefinition(GeneratedDefinitionModel):
    rules: list[TestPlanRuleDefinition] = Field(default_factory=list)


class ExplicitTestGroupDefinition(GeneratedDefinitionModel):
    group: str
    stress_points: list[dict[str, Any]]


class ExplicitTestPlanDefinition(GeneratedDefinitionModel):
    name: str
    test_type: str
    dimensions: dict[str, Any] = Field(default_factory=dict)
    device_state: str | None = None
    test_groups: list[ExplicitTestGroupDefinition]


class ProjectGenerationDefinition(GeneratedDefinitionModel):
    schema_version: str
    project: ProjectMetadata
    constants: dict[str, Any] = Field(default_factory=dict)
    mappings: dict[str, dict[str, Any]] = Field(default_factory=dict)
    formatters: dict[str, FormatterDefinition] = Field(default_factory=dict)
    sources: dict[str, InlineSource | JsonSource | CsvSource | ExcelSource] = Field(default_factory=dict)
    dut: DutDefinition | None = None
    groups: GroupsDefinition = Field(default_factory=GroupsDefinition)
    hardware: HardwareDefinition | None = None
    power_resources: dict[str, PowerResourceDefinition] = Field(default_factory=dict)
    device_states: dict[str, DeviceStateDefinition] = Field(default_factory=dict)
    test_plans: list[ExplicitTestPlanDefinition] = Field(default_factory=list)
    test_plan_generation: TestPlanGenerationDefinition = Field(default_factory=TestPlanGenerationDefinition)
    output: dict[str, Any] = Field(default_factory=dict)
