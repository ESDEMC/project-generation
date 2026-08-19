import pathlib
from typing import Any

from pydantic import PrivateAttr, model_validator

from .generated_models import (
    AllPartitionDefinition,
    AllocationDefinition,
    BiasDefinition,
    CsvSource,
    DeviceStateDefinition,
    DeviceStateRuleDefinition,
    DimensionDefinition,
    DimensionValueDefinition,
    DutDefinition,
    EachPartitionDefinition,
    ExcelSource,
    ExplicitGroupDefinition,
    ExplicitTestGroupDefinition,
    ExplicitTestPlanDefinition,
    FormatterDefinition,
    GroupByPartitionDefinition,
    GroupGenerationRule,
    HardwareDefinition,
    GroupsDefinition,
    InlineSource,
    InlineSourceReference,
    JsonSource,
    NameFieldDefinition,
    NameTemplateDefinition,
    NamedSourceReference,
    OverrideDefinition,
    OverrideScope,
    PowerDomainDefinition,
    PowerResourceDefinition,
    PowerSequenceTimingDefinition,
    ProjectGenerationDefinition as GeneratedProjectGenerationDefinition,
    ProjectMetadata,
    SelectionDefinition,
    SourceFieldMapping,
    TestGroupsDefinition,
    TestPlanGenerationDefinition,
    TestPlanRuleDefinition,
    TimingDefinition,
    ValueDefinition,
)

JsonValue = Any
SourceDefinition = InlineSource | JsonSource | CsvSource | ExcelSource
SourceFieldMappingDefinition = str | SourceFieldMapping
PinSourceReference = NamedSourceReference | InlineSourceReference
PartitionDefinition = EachPartitionDefinition | AllPartitionDefinition | GroupByPartitionDefinition


class ProjectGenerationDefinition(GeneratedProjectGenerationDefinition):
    _definition_path: pathlib.Path | None = PrivateAttr(default=None)

    @property
    def definition_path(self) -> pathlib.Path | None:
        return self._definition_path

    @property
    def definition_directory(self) -> pathlib.Path | None:
        return self._definition_path.parent if self._definition_path is not None else None

    @model_validator(mode="after")
    def validate_semantics(self) -> "ProjectGenerationDefinition":
        if self.project.name is None and self.project.source is None:
            raise ValueError("project requires either name or source")

        for rule in self.test_plan_generation.rules:
            names = [dimension.name for dimension in rule.dimensions]
            if len(names) != len(set(names)):
                raise ValueError(f'test plan rule "{rule.id}" contains duplicate dimension names')

            partition = rule.groups.partition
            if getattr(partition, "mode", None) == "group_by" and not partition.fields:
                raise ValueError("group_by partition requires at least one field")

            for override in rule.overrides:
                if not override.set and not override.exclude:
                    raise ValueError("override must define set values or exclude=true")

        return self

    @property
    def name(self) -> str | None:
        return self.project.name

    @classmethod
    def load(cls, path: str | pathlib.Path) -> "ProjectGenerationDefinition":
        path = pathlib.Path(path).resolve()
        text = path.read_text(encoding="utf-8")
        suffix = path.suffix.lower()

        if suffix == ".json":
            definition = cls.model_validate_json(text)
            definition._definition_path = path
            return definition
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
            definition = cls.model_validate(data)
            definition._definition_path = path
            return definition

        raise ValueError(f"Unsupported generation definition format {suffix!r}; expected .json, .yaml, or .yml")


__all__ = [
    "AllPartitionDefinition",
    "AllocationDefinition",
    "BiasDefinition",
    "CsvSource",
    "DeviceStateDefinition",
    "DeviceStateRuleDefinition",
    "DimensionDefinition",
    "DimensionValueDefinition",
    "DutDefinition",
    "EachPartitionDefinition",
    "ExcelSource",
    "ExplicitGroupDefinition",
    "ExplicitTestGroupDefinition",
    "ExplicitTestPlanDefinition",
    "FormatterDefinition",
    "GroupByPartitionDefinition",
    "GroupGenerationRule",
    "HardwareDefinition",
    "GroupsDefinition",
    "InlineSource",
    "InlineSourceReference",
    "JsonSource",
    "JsonValue",
    "NameFieldDefinition",
    "NameTemplateDefinition",
    "NamedSourceReference",
    "OverrideDefinition",
    "OverrideScope",
    "PartitionDefinition",
    "PinSourceReference",
    "PowerDomainDefinition",
    "PowerResourceDefinition",
    "PowerSequenceTimingDefinition",
    "ProjectGenerationDefinition",
    "ProjectMetadata",
    "SelectionDefinition",
    "SourceDefinition",
    "SourceFieldMapping",
    "SourceFieldMappingDefinition",
    "TestGroupsDefinition",
    "TestPlanGenerationDefinition",
    "TestPlanRuleDefinition",
    "TimingDefinition",
    "ValueDefinition",
]
