from dataclasses import dataclass

from project_generation.definition.models import ProjectGenerationDefinition
from project_generation.generation.models import (
    GeneratedDeviceState,
    GeneratedGroup,
    GeneratedPin,
    GeneratedProject,
    GeneratedTestPlan,
)


@dataclass(frozen=True, kw_only=True)
class GenerationSnapshot:
    """Intermediate results captured from one project-generation pass."""

    definition: ProjectGenerationDefinition
    pins: tuple[GeneratedPin, ...]
    groups: tuple[GeneratedGroup, ...]
    device_states: tuple[GeneratedDeviceState, ...]
    test_plans: tuple[GeneratedTestPlan, ...]
    generated_project: GeneratedProject
