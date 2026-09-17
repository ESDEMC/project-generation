import importlib.util
import pathlib

import pytest

from project_generation import (
    PowerResourceResolutionError,
    StressSupplyResolutionError,
    ProjectGenerationError,
    ProjectGenerationProcessor,
    load_project_definition,
)
from project_generation.application.workflows import bind_input_files
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
    definition = bind_input_files(
        definition,
        {"input_file": input_path.resolve()},
    )
    return ProjectGenerationProcessor().process(
        definition,
        base_directory=module.DEFAULT_DEFINITION_PATH.resolve().parent,
    )


def compatible_input_paths() -> list[pathlib.Path]:
    return [
        path for path in sorted(INPUT.glob("*.json"))
        if path.name not in INCOMPATIBLE_WITH_EXAMPLE_HARDWARE
    ]


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

    for input_path in compatible_input_paths():
        project = process_realis_definition(module, input_path)
        expected_temperature = float(project.metadata["temperature"])

        assert project.test_plans
        assert all(plan.temperature_control is not None for plan in project.test_plans)
        assert all(plan.temperature_control.temperature == expected_temperature for plan in project.test_plans)
        assert all(plan.temperature_control.enabled for plan in project.test_plans)
        assert all(plan.temperature_control.soak_time == 0.0 for plan in project.test_plans)
        assert all(plan.temperature_control.start_tolerance == 10.0 for plan in project.test_plans)
        assert all(plan.temperature_control.timeout == 900.0 for plan in project.test_plans)


def test_realis_stress_current_is_normalized_from_milliamps() -> None:
    module = load_example_module()

    for input_path in compatible_input_paths():
        project = process_realis_definition(module, input_path)
        raw = __import__("json").loads(input_path.read_text(encoding="utf-8"))

        assert float(project.metadata["stress_current"]) == pytest.approx(float(raw["StressCurrent"]) * 0.001)


def test_realis_signal_tests_use_current_source_with_voltage_compliance() -> None:
    module = load_example_module()

    for input_path in compatible_input_paths():
        project = process_realis_definition(module, input_path)
        groups_by_id = {group.id: group for group in project.groups}
        stress_current = float(project.metadata["stress_current"])
        signal_plans = [plan for plan in project.test_plans if plan.generation_rule_id == "signal_tests"]
        assert signal_plans

        for plan in signal_plans:
            polarity = plan.dimensions["polarity"]
            for test_group in plan.test_groups:
                group = groups_by_id[test_group.group_id]
                v_max = float(group.parameters["v_max"])
                v_min = float(group.parameters["v_min"])
                points = list(test_group.stress_points)

                assert len(points) == 2
                assert all(point.values["source_mode"] == "current" for point in points)
                assert test_group.pin_ids is not None
                assert len(test_group.pin_ids) == 1
                assert test_group.pin_ids[0] in group.pin_ids
                assert all(float(point.values["base_level"]) == pytest.approx(0.0) for point in points)

                peaks = [float(point.values["peak_level"]) for point in points]
                base_limits = [float(point.values["base_limit"]) for point in points]
                peak_limits = [float(point.values["peak_limit"]) for point in points]
                if polarity == "POSITIVE":
                    assert peaks == pytest.approx([stress_current, stress_current])
                    expected = [v_max, v_max * 1.5]
                    assert base_limits == pytest.approx(expected)
                    assert peak_limits == pytest.approx(expected)
                else:
                    span = abs(v_max - v_min)
                    assert peaks == pytest.approx([-stress_current, -stress_current])
                    expected = [-span * 0.25, -span * 0.5]
                    assert base_limits == pytest.approx(expected)
                    assert peak_limits == pytest.approx(expected)
                    assert all(peak * voltage > 0.0 for peak, voltage in zip(peaks, peak_limits, strict=True))


def test_realis_supply_tests_use_vmax_as_base() -> None:
    module = load_example_module()

    for input_path in compatible_input_paths():
        project = process_realis_definition(module, input_path)
        groups_by_id = {group.id: group for group in project.groups}
        supply_plans = [plan for plan in project.test_plans if plan.generation_rule_id == "supply_tests"]
        assert supply_plans

        for plan in supply_plans:
            for test_group in plan.test_groups:
                group = groups_by_id[test_group.group_id]
                v_max = float(group.parameters["v_max"])
                assert all(float(point.values["base_level"]) == pytest.approx(v_max) for point in test_group.stress_points)
                assert all(float(point.values["base_limit"]) == pytest.approx(0.2) for point in test_group.stress_points)
                assert all(float(point.values["peak_limit"]) == pytest.approx(0.2) for point in test_group.stress_points)

