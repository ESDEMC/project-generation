import json
import pathlib

from project_generation.diagnostics import GenerationDiagnostic, GenerationDiagnostics, ProjectGenerationError
from project_generation.ganging import (
    GangingCandidate,
    GangingPolicy,
    NoGangingPolicy,
    SameVoltageGangingPolicy,
    get_ganging_policy,
)
from .extensions.latchup_project.latchup_adapter import adapt_to_latchup_project
from project_generation.models import ProjectGenerationDefinition
from project_generation.processing import (
    GroupPartition,
    GroupRecord,
    StressPoint,
    TestPlanCandidate,
    expand_dimensions,
    expand_rule,
    expand_stress_parameters,
    generate_range,
    partition_groups,
    resolve_group_values,
    resolve_group_values_and_exclusion,
)
from project_generation.project_processor import (
    GeneratedDeviceState,
    GeneratedGroup,
    GeneratedGroupState,
    GeneratedPin,
    GeneratedPowerAssignment,
    GeneratedPowerDomain,
    GeneratedPowerSequenceStep,
    GeneratedProject,
    GeneratedTestGroup,
    GeneratedTestPlan,
    ProjectGenerationProcessor,
    apply_record_mapping,
    load_source_records,
    select_json_records,
)
from project_generation.serialization import (
    generated_project_to_dict,
    generated_project_to_json,
    write_generated_project,
)
from project_generation.validation import validate_project_definition


def load_project_definition(path: str | pathlib.Path) -> ProjectGenerationDefinition:
    return ProjectGenerationDefinition.load(path)


def process_project_definition(path: str | pathlib.Path) -> GeneratedProject:
    path = pathlib.Path(path)
    definition = load_project_definition(path)
    return ProjectGenerationProcessor().process(definition, base_directory=path.parent)


def write_json_schema(path: str | pathlib.Path) -> None:
    path = pathlib.Path(path)
    path.write_text(json.dumps(ProjectGenerationDefinition.model_json_schema(), indent=2), encoding="utf-8")


__all__ = [
    "GangingCandidate",
    "GangingPolicy",
    "NoGangingPolicy",
    "SameVoltageGangingPolicy",
    "GeneratedDeviceState",
    "GeneratedGroup",
    "GeneratedGroupState",
    "GeneratedPin",
    "GeneratedPowerAssignment",
    "GeneratedPowerDomain",
    "GeneratedPowerSequenceStep",
    "GeneratedProject",
    "GeneratedTestGroup",
    "GeneratedTestPlan",
    "GenerationDiagnostic",
    "GenerationDiagnostics",
    "GroupPartition",
    "GroupRecord",
    "ProjectGenerationDefinition",
    "ProjectGenerationError",
    "ProjectGenerationProcessor",
    "StressPoint",
    "TestPlanCandidate",
    "adapt_to_latchup_project",
    "apply_record_mapping",
    "expand_dimensions",
    "expand_rule",
    "expand_stress_parameters",
    "generate_range",
    "generated_project_to_dict",
    "generated_project_to_json",
    "get_ganging_policy",
    "load_project_definition",
    "load_source_records",
    "partition_groups",
    "process_project_definition",
    "resolve_group_values",
    "resolve_group_values_and_exclusion",
    "select_json_records",
    "validate_project_definition",
    "write_generated_project",
    "write_json_schema",
]
