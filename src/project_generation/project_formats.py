import pathlib
from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import Any

from project_generation.latchup_packaging import write_latchup_project_package
from project_generation.project_processor import GeneratedProject


class ProjectFormat(ABC):
    """Writes a neutral generated project in a concrete project format."""

    @abstractmethod
    def write(
        self,
        project: GeneratedProject,
        output_directory: str | pathlib.Path,
        *,
        project_metadata: Mapping[str, Any] | None = None,
    ) -> pathlib.Path:
        """Write the concrete project and return its primary project file."""


class LatchUpProjectFormat(ProjectFormat):
    """Concrete format for the latch-up application's project package."""

    def write(
        self,
        project: GeneratedProject,
        output_directory: str | pathlib.Path,
        *,
        project_metadata: Mapping[str, Any] | None = None,
    ) -> pathlib.Path:
        return write_latchup_project_package(project, output_directory, project_metadata=project_metadata)


DEFAULT_PROJECT_FORMAT = LatchUpProjectFormat()
