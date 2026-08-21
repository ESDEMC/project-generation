import importlib.util
import pathlib

from project_generation import (
    PowerResourceResolutionError,
    StressSupplyResolutionError,
    ProjectGenerationError,
    ProjectGenerationProcessor,
    load_project_definition,
)
from project_generation.application.workflows import replace_source_paths
from tests.support.paths import REALIS

EXAMPLE = REALIS / "generate_projects.py"
INPUT = REALIS / "input"
INCOMPATIBLE_WITH_EXAMPLE_HARDWARE: set[str] = set()


def load_example_module():
    spec = importlib.util.spec_from_file_location("generate_realis_projects", EXAMPLE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def process_realis_definition(module, input_path: pathlib.Path):
    definition = load_project_definition(module.DEFAULT_DEFINITION_PATH)
    definition = replace_source_paths(definition, {name: input_path.resolve() for name in module.REALIS_SOURCE_NAMES})
    return ProjectGenerationProcessor().process(
        definition,
        base_directory=module.DEFAULT_DEFINITION_PATH.resolve().parent,
    )


def test_realis_device_states_are_checked_against_example_hardware() -> None:
    module = load_example_module()
    incompatible = set()

    for input_path in sorted(INPUT.glob("*.json")):
        try:
            process_realis_definition(module, input_path)
        except PowerResourceResolutionError as error:
            assert error.issues
            assert all(issue.candidates for issue in error.issues)
            assert "Power resources checked:" in error.format_user_report()
            incompatible.add(input_path.name)
        except StressSupplyResolutionError as error:
            assert error.issues
            assert all(issue.candidates for issue in error.issues)
            assert "Stress resources checked:" in error.format_user_report()
            incompatible.add(input_path.name)

    assert incompatible == INCOMPATIBLE_WITH_EXAMPLE_HARDWARE


def test_realis_example_generates_compatible_project_packages(tmp_path: pathlib.Path) -> None:
    module = load_example_module()
    input_paths = [
        path for path in sorted(INPUT.glob("*.json")) if path.name not in INCOMPATIBLE_WITH_EXAMPLE_HARDWARE
    ]

    assert input_paths

    for input_path in input_paths:
        project_path = module.generate_realis_project(module.DEFAULT_DEFINITION_PATH, input_path, tmp_path)
        assert project_path.exists()
        assert project_path.suffix == ".Prj"
        assert list(project_path.parent.glob("*.LuDut"))
        assert list((project_path.parent / "Testing").glob("*.LuTstPlan"))


def test_realis_temperature_control_uses_project_temperature() -> None:
    module = load_example_module()

    for input_path in sorted(INPUT.glob("*.json")):
        project = process_realis_definition(module, input_path)
        expected_temperature = float(project.metadata["temperature"])

        assert project.test_plans
        assert all(plan.temperature_control is not None for plan in project.test_plans)
        assert all(plan.temperature_control.temperature == expected_temperature for plan in project.test_plans)
        assert all(plan.temperature_control.enabled for plan in project.test_plans)
        assert all(plan.temperature_control.soak_time == 0.0 for plan in project.test_plans)
        assert all(plan.temperature_control.start_tolerance == 10.0 for plan in project.test_plans)
        assert all(plan.temperature_control.timeout == 900.0 for plan in project.test_plans)
