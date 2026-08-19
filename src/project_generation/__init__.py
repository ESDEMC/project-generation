import pathlib
from collections.abc import Mapping
from typing import Any

from .application.ports import ProjectWriter
from .definition.models import ProjectGenerationDefinition
from .definition.validation import validate_project_definition
from .diagnostics import (
    GenerationDiagnostics,
    PowerResourceCandidateDiagnostic,
    PowerResourceResolutionError,
    PowerResourceResolutionIssue,
    ProjectGenerationError,
    StressSupplyCandidateDiagnostic,
    StressSupplyResolutionError,
    StressSupplyResolutionIssue,
)
from .generation.models import GeneratedProject
from .generation.processor import ProjectGenerationProcessor


def load_project_definition(path: str | pathlib.Path) -> ProjectGenerationDefinition:
    return ProjectGenerationDefinition.load(path)


def process_project_definition(path: str | pathlib.Path) -> GeneratedProject:
    definition = load_project_definition(path)
    return ProjectGenerationProcessor().process(definition)


def generate_project(
    definition: str | pathlib.Path | ProjectGenerationDefinition,
    output_directory: str | pathlib.Path,
    *,
    project_writer: ProjectWriter | None = None,
    base_directory: str | pathlib.Path | None = None,
    project_metadata: Mapping[str, Any] | None = None,
) -> pathlib.Path:
    if isinstance(definition, ProjectGenerationDefinition):
        generated = ProjectGenerationProcessor().process(definition, base_directory=base_directory)
    else:
        generated = process_project_definition(definition)

    if project_writer is None:
        from .infrastructure.latchup_project.writer import LatchUpProjectWriter

        project_writer = LatchUpProjectWriter()

    return project_writer.write(generated, output_directory, project_metadata=project_metadata)


__all__ = [
    "GeneratedProject",
    "GenerationDiagnostics",
    "ProjectGenerationDefinition",
    "PowerResourceCandidateDiagnostic",
    "PowerResourceResolutionError",
    "PowerResourceResolutionIssue",
    "ProjectGenerationError",
    "ProjectGenerationProcessor",
    "StressSupplyCandidateDiagnostic",
    "StressSupplyResolutionError",
    "StressSupplyResolutionIssue",
    "ProjectWriter",
    "generate_project",
    "load_project_definition",
    "process_project_definition",
    "validate_project_definition",
]
