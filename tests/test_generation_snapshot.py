from project_generation.definition.models import ProjectGenerationDefinition
from project_generation.generation.processor import ProjectGenerationProcessor
from tests.support.paths import EXPLICIT_PROJECT


def test_process_with_snapshot_exposes_generation_stages() -> None:
    definition = ProjectGenerationDefinition.load(EXPLICIT_PROJECT)
    processor = ProjectGenerationProcessor()

    snapshot = processor.process_with_snapshot(definition)

    assert snapshot.generated_project == processor.process(definition)
    assert snapshot.pins == snapshot.generated_project.pins
    assert snapshot.groups == snapshot.generated_project.groups
    assert snapshot.device_states == snapshot.generated_project.device_states
    assert snapshot.test_plans == snapshot.generated_project.test_plans
