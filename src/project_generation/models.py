import json
import pathlib
from enum import StrEnum
from typing import Any, Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel, field_validator, model_validator

JsonValue = Any


class DefinitionModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class ProjectMetadata(DefinitionModel):
    name: str
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class InlineSource(DefinitionModel):
    type: Literal["inline"] = "inline"
    records: list[dict[str, JsonValue]]


class SourceFieldMapping(DefinitionModel):
    from_: str = Field(alias="from")
    mapping: str | None = None
    formatter: str | None = None


SourceFieldMappingDefinition = str | SourceFieldMapping


class JsonSource(DefinitionModel):
    type: Literal["json"] = "json"
    path: str
    select: str | None = None
    mapping: dict[str, SourceFieldMappingDefinition] = Field(default_factory=dict)


class CsvSource(DefinitionModel):
    type: Literal["csv"] = "csv"
    path: str
    mapping: dict[str, SourceFieldMappingDefinition] = Field(default_factory=dict)


class ExcelSource(DefinitionModel):
    type: Literal["excel"] = "excel"
    path: str
    sheet: str | int | None = None
    mapping: dict[str, SourceFieldMappingDefinition] = Field(default_factory=dict)


SourceDefinition = Annotated[InlineSource | JsonSource | CsvSource | ExcelSource, Field(discriminator="type")]


class NamedSourceReference(DefinitionModel):
    source: str


class InlineSourceReference(DefinitionModel):
    source: SourceDefinition


PinSourceReference = NamedSourceReference | InlineSourceReference


class DutDefinition(DefinitionModel):
    name: str
    pins: PinSourceReference


class ExplicitGroupDefinition(DefinitionModel):
    name: str
    group_type: str
    pins: list[str]
    parameters: dict[str, JsonValue] = Field(default_factory=dict)


class QueryDefinition(RootModel[dict[str, JsonValue]]):
    pass


class SelectionDefinition(DefinitionModel):
    where: dict[str, JsonValue] = Field(default_factory=dict)


class ValueReference(DefinitionModel):
    from_: str = Field(alias="from")


class NameFieldDefinition(DefinitionModel):
    source: str
    mapping: str | None = None
    formatter: str | None = None


class NameTemplateDefinition(DefinitionModel):
    template: str
    fields: dict[str, NameFieldDefinition] = Field(default_factory=dict)


class GroupGenerationRule(DefinitionModel):
    id: str
    select: SelectionDefinition = Field(default_factory=SelectionDefinition)
    group_by: list[str]
    set: dict[str, JsonValue] = Field(default_factory=dict)
    name: NameTemplateDefinition


class GroupsDefinition(DefinitionModel):
    external: bool = False
    explicit: list[ExplicitGroupDefinition] = Field(default_factory=list)
    generation: list[GroupGenerationRule] = Field(default_factory=list)


class FormatterDefinition(DefinitionModel):
    type: str
    separator: str | None = None
    decimal_places: int | None = None


class PowerResourceDefinition(DefinitionModel):
    role: str | None = None
    parameters: dict[str, JsonValue] = Field(default_factory=dict)


class BiasDefinition(DefinitionModel):
    mode: str
    level: JsonValue = None


class PowerSequenceTimingDefinition(DefinitionModel):
    delay: float = 0.0
    after: str | None = None


class TimingDefinition(DefinitionModel):
    power_on: PowerSequenceTimingDefinition | None = None
    power_off: PowerSequenceTimingDefinition | None = None


class PowerDomainDefinition(DefinitionModel):
    name: str
    groups: list[str]
    assignment: str
    bias: BiasDefinition
    timing: TimingDefinition | None = None


class AllocationDefinition(DefinitionModel):
    mode: Literal["direct", "automatic", "hybrid"]
    strategy: str | None = None
    reserve: list[str] = Field(default_factory=list)
    ganging_policy: str | None = None


class DeviceStateRuleDefinition(DefinitionModel):
    when: dict[str, JsonValue]
    set: dict[str, JsonValue]


class DeviceStateDefinition(DefinitionModel):
    extends: str | None = None
    power_domains: list[PowerDomainDefinition] = Field(default_factory=list)
    allocation: AllocationDefinition | None = None
    rules: list[DeviceStateRuleDefinition] = Field(default_factory=list)


class EachPartitionDefinition(DefinitionModel):
    mode: Literal["each"]


class AllPartitionDefinition(DefinitionModel):
    mode: Literal["all"]


class GroupByPartitionDefinition(DefinitionModel):
    mode: Literal["group_by"]
    fields: list[str]

    @field_validator("fields")
    @classmethod
    def fields_must_not_be_empty(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("group_by partition requires at least one field")
        return value


PartitionDefinition = Annotated[
    EachPartitionDefinition | AllPartitionDefinition | GroupByPartitionDefinition,
    Field(discriminator="mode"),
]


class TestGroupsDefinition(DefinitionModel):
    select: SelectionDefinition = Field(default_factory=SelectionDefinition)
    partition: PartitionDefinition


class DimensionValueDefinition(DefinitionModel):
    value: JsonValue
    set: dict[str, JsonValue] = Field(default_factory=dict)


class DimensionDefinition(DefinitionModel):
    name: str
    values: list[DimensionValueDefinition | str | int | float | bool | None]

    @field_validator("values", mode="before")
    @classmethod
    def normalize_compact_values(cls, value: Any) -> Any:
        if not isinstance(value, list):
            return value
        return [item if isinstance(item, dict) and "value" in item else {"value": item} for item in value]

    @field_validator("values")
    @classmethod
    def values_must_not_be_empty(cls, value: list[DimensionValueDefinition]) -> list[DimensionValueDefinition]:
        if not value:
            raise ValueError("dimension requires at least one value")
        return value


class OverrideScope(StrEnum):
    PLAN = "plan"
    GROUP = "group"


class OverrideDefinition(DefinitionModel):
    scope: OverrideScope = OverrideScope.PLAN
    when: dict[str, JsonValue]
    set: dict[str, JsonValue] = Field(default_factory=dict)
    exclude: bool = False

    @model_validator(mode="after")
    def require_action(self) -> "OverrideDefinition":
        if not self.set and not self.exclude:
            raise ValueError("override must define set values or exclude=true")
        return self


class TestPlanRuleDefinition(DefinitionModel):
    id: str
    groups: TestGroupsDefinition
    dimensions: list[DimensionDefinition] = Field(default_factory=list)
    template: dict[str, JsonValue]
    overrides: list[OverrideDefinition] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_dimensions(self) -> "TestPlanRuleDefinition":
        names = [dimension.name for dimension in self.dimensions]
        if len(names) != len(set(names)):
            raise ValueError("dimension names must be unique within a rule")
        return self


class TestPlanGenerationDefinition(DefinitionModel):
    rules: list[TestPlanRuleDefinition] = Field(default_factory=list)


class ExplicitTestGroupDefinition(DefinitionModel):
    group: str
    stress_points: list[dict[str, JsonValue]]


class ExplicitTestPlanDefinition(DefinitionModel):
    name: str
    test_type: str
    dimensions: dict[str, JsonValue] = Field(default_factory=dict)
    device_state: str | None = None
    test_groups: list[ExplicitTestGroupDefinition]


class ProjectGenerationDefinition(DefinitionModel):
    schema_version: str
    project: ProjectMetadata
    constants: dict[str, JsonValue] = Field(default_factory=dict)
    mappings: dict[str, dict[str, JsonValue]] = Field(default_factory=dict)
    formatters: dict[str, FormatterDefinition] = Field(default_factory=dict)
    sources: dict[str, SourceDefinition] = Field(default_factory=dict)
    dut: DutDefinition | None = None
    groups: GroupsDefinition = Field(default_factory=GroupsDefinition)
    power_resources: dict[str, PowerResourceDefinition] = Field(default_factory=dict)
    device_states: dict[str, DeviceStateDefinition] = Field(default_factory=dict)
    test_plans: list[ExplicitTestPlanDefinition] = Field(default_factory=list)
    test_plan_generation: TestPlanGenerationDefinition = Field(default_factory=TestPlanGenerationDefinition)
    output: dict[str, JsonValue] = Field(default_factory=dict)

    @classmethod
    def load(cls, path: str | pathlib.Path) -> "ProjectGenerationDefinition":
        path = pathlib.Path(path)
        text = path.read_text(encoding="utf-8")
        suffix = path.suffix.lower()

        if suffix == ".json":
            return cls.model_validate_json(text)
        if suffix in {".yaml", ".yml"}:
            try:
                import yaml
            except ImportError as error:
                raise RuntimeError(
                    "YAML generation files require PyYAML. Install project-generation[yaml] or PyYAML directly."
                ) from error

            data = yaml.safe_load(text)
            if data is None:
                data = {}
            if not isinstance(data, dict):
                raise ValueError(f"Generation definition must contain a top-level object: {path}")
            return cls.model_validate(data)

        raise ValueError(f"Unsupported generation definition format {suffix!r}; expected .json, .yaml, or .yml")

    def write_schema(self, path: str | pathlib.Path) -> None:
        path = pathlib.Path(path)
        path.write_text(json.dumps(self.model_json_schema(), indent=2), encoding="utf-8")
