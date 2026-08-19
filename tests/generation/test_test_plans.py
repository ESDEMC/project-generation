from tests.support.paths import EXPLICIT_PROJECT, STRESS_SERIES_AND_OVERRIDES
from project_generation import process_project_definition


def test_explicit_test_plan_is_preserved() -> None:
    generated = process_project_definition(EXPLICIT_PROJECT)

    assert len(generated.test_plans) == 1
    plan = generated.test_plans[0]
    assert plan.name == "IN5V5_HIGH_POSITIVE"
    assert plan.test_type == "SIGNAL"
    assert plan.device_state == "logic_high"
    assert len(plan.test_groups) == 1
    assert [point.values["stress_voltage"] for point in plan.test_groups[0].stress_points] == [5.5, 6.0, 6.5]


def test_generated_customer_plans_expand_dimensions_and_stress_series() -> None:
    generated = process_project_definition(STRESS_SERIES_AND_OVERRIDES)

    assert len(generated.test_plans) == 4
    plan = next(plan for plan in generated.test_plans if plan.name == "OUT_A_NEGATIVE")
    assert plan.dimensions == {"polarity": "NEGATIVE"}
    assert plan.device_state is None
    assert len(plan.test_groups) == 1
    assert [point.values for point in plan.test_groups[0].stress_points] == [
        {"compliance": 0.025, "pulse_width": 0.075, "stress_voltage": 0.0},
        {"compliance": 0.025, "pulse_width": 0.075, "stress_voltage": -0.5},
        {"compliance": 0.025, "pulse_width": 0.075, "stress_voltage": -1.0},
        {"compliance": 0.025, "pulse_width": 0.075, "stress_voltage": -1.5},
    ]


def test_generated_test_plan_ids_are_deterministic() -> None:
    first = process_project_definition(STRESS_SERIES_AND_OVERRIDES)
    second = process_project_definition(STRESS_SERIES_AND_OVERRIDES)

    assert [plan.id for plan in first.test_plans] == [plan.id for plan in second.test_plans]
