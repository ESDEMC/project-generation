import json
import pathlib
from collections.abc import Mapping
from typing import Any

from project_generation.diagnostics import GenerationDiagnostic, GenerationDiagnostics, ProjectGenerationError
from project_generation.ganging import (
    GangingCandidate,
    GangingPolicy,
    NoGangingPolicy,
    SameVoltageGangingPolicy,
    get_ganging_policy,
)
from .extensions.latchup_project.latchup_adapter import (
    adapt_to_latchup_project,
    LatchUpProjectArtifacts,
    LatchUpProjectCoreAdapter,
)
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
from project_generation.workflows import raise_for_diagnostics, replace_source_paths
from project_generation.latchup_packaging import safe_file_name, write_latchup_project_package
from project_generation.project_formats import DEFAULT_PROJECT_FORMAT, LatchUpProjectFormat, ProjectFormat


def load_project_definition(path: str | pathlib.Path) -> ProjectGenerationDefinition:
    return ProjectGenerationDefinition.load(path)


def process_project_definition(path: str | pathlib.Path) -> GeneratedProject:
    path = pathlib.Path(path)
    definition = load_project_definition(path)
    return ProjectGenerationProcessor().process(definition, base_directory=path.parent)



def generate_project(
    definition: str | pathlib.Path | ProjectGenerationDefinition,
    output_directory: str | pathlib.Path,
    *,
    project_format: ProjectFormat | None = None,
    base_directory: str | pathlib.Path | None = None,
    project_metadata: Mapping[str, Any] | None = None,
) -> pathlib.Path:
    """Generate and write a concrete project.

    The latch-up project package is the default concrete format. Pass another
    ProjectFormat implementation when additional project formats are introduced.
    """
    if isinstance(definition, ProjectGenerationDefinition):
        if base_directory is None:
            raise ValueError("base_directory is required when generating from a loaded definition")
        generated = ProjectGenerationProcessor().process(definition, base_directory=pathlib.Path(base_directory))
    else:
        generated = process_project_definition(definition)

    concrete_format = project_format or DEFAULT_PROJECT_FORMAT
    return concrete_format.write(generated, output_directory, project_metadata=project_metadata)


def write_json_schema(path: str | pathlib.Path) -> None:
    path = pathlib.Path(path)
    path.write_text(json.dumps(ProjectGenerationDefinition.model_json_schema(), indent=2), encoding="utf-8")


__all__ = [
    "GangingCandidate",
    "generate_project",
    "ProjectFormat",
    "LatchUpProjectFormat",
    "DEFAULT_PROJECT_FORMAT",
    "LatchUpProjectArtifacts",
    "LatchUpProjectCoreAdapter",
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
    "raise_for_diagnostics",
    "replace_source_paths",
    "safe_file_name",
    "write_latchup_project_package",
]
