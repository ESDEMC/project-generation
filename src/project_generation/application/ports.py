import pathlib
from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import Any

from project_generation.generation.models import GeneratedProject


class ProjectWriter(ABC):
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
