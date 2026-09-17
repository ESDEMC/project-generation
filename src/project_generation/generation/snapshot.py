from dataclasses import dataclass
from enum import StrEnum

from project_generation.definition.models import ProjectGenerationDefinition
from project_generation.diagnostics import GenerationDiagnostic
from project_generation.generation.models import (
    GeneratedDeviceState,
    GeneratedGroup,
    GeneratedPin,
    GeneratedProject,
    GeneratedTestPlan,
)


class GenerationStageStatus(StrEnum):
    COMPLETE = "complete"
    FAILED = "failed"
    NOT_ATTEMPTED = "not_attempted"


@dataclass(frozen=True, kw_only=True)
class GenerationStageResult:
    name: str
    status: GenerationStageStatus
    produced_count: int = 0
    diagnostic: GenerationDiagnostic | None = None


@dataclass(frozen=True, kw_only=True)
class GenerationSnapshot:
    """Intermediate results captured from one project-generation pass."""

    definition: ProjectGenerationDefinition
    pins: tuple[GeneratedPin, ...]
    groups: tuple[GeneratedGroup, ...]
    device_states: tuple[GeneratedDeviceState, ...]
    test_plans: tuple[GeneratedTestPlan, ...]
    generated_project: GeneratedProject
    stages: tuple[GenerationStageResult, ...] = ()
    diagnostics: tuple[GenerationDiagnostic, ...] = ()

    def stage(self, name: str) -> GenerationStageResult | None:
        return next((stage for stage in self.stages if stage.name == name), None)
