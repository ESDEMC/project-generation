from pathlib import Path
from typing import Protocol, TypeVar

from project_generation import GeneratedProject

from .requests import GenerateProjectRequest

ArtifactsT = TypeVar("ArtifactsT")


class ProjectWriter(Protocol[ArtifactsT]):
    def write(self, artifacts: ArtifactsT, *, request: GenerateProjectRequest) -> Path:
        ...


class ProjectGenerationAdapter(Protocol[ArtifactsT]):
    def adapt(self, project: GeneratedProject) -> ArtifactsT:
        ...
