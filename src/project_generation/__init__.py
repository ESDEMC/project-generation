import pathlib
from collections.abc import Mapping
from typing import Any

from .application.ports import ProjectWriter
from .definition.models import ProjectGenerationDefinition
from .definition.validation import validate_project_definition
from .diagnostics import GenerationDiagnostics, ProjectGenerationError
from .generation.models import GeneratedProject
from .generation.processor import ProjectGenerationProcessor


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
    project_writer: ProjectWriter | None = None,
    base_directory: str | pathlib.Path | None = None,
    project_metadata: Mapping[str, Any] | None = None,
) -> pathlib.Path:
    if isinstance(definition, ProjectGenerationDefinition):
        if base_directory is None:
            raise ValueError("base_directory is required when generating from a loaded definition")
        generated = ProjectGenerationProcessor().process(definition, base_directory=pathlib.Path(base_directory))
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
    "ProjectGenerationError",
    "ProjectGenerationProcessor",
    "ProjectWriter",
    "generate_project",
    "load_project_definition",
    "process_project_definition",
    "validate_project_definition",
]
