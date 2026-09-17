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


def test_generated_signal_test_groups_expand_per_pin() -> None:
    from project_generation import ProjectGenerationDefinition, ProjectGenerationProcessor

    definition = ProjectGenerationDefinition.model_validate(
        {
            "schema_version": "1.0",
            "project": {"name": "Per-pin signals"},
            "dut": {
                "name": "DUT",
                "pins": {
                    "source": {
                        "type": "inline",
                        "records": [
                            {"designator": "1", "name": "IN_A"},
                            {"designator": "2", "name": "IN_B"},
                        ],
                    }
                },
            },
            "groups": {
                "explicit": [
                    {"name": "INPUTS", "group_type": "INPUT", "pins": ["1", "2"], "parameters": {"v_max": 5.0}}
                ]
            },
            "test_plan_generation": {
                "rules": [
                    {
                        "id": "signals",
                        "groups": {
                            "select": {"where": {"group_type": "INPUT"}},
                            "partition": {"mode": "each"},
                        },
                        "template": {
                            "name": "SIGNALS",
                            "test_type": "SIGNAL",
                            "stress_parameters": {
                                "source_mode": "voltage",
                                "base_level": 0.0,
                                "base_limit": 0.1,
                                "peak_level": 5.0,
                                "peak_limit": 0.1,
                                "pulse_width": 0.01,
                            },
                        },
                    }
                ]
            },
        }
    )

    project = ProjectGenerationProcessor().process(definition)

    assert len(project.test_plans) == 1
    plan = project.test_plans[0]
    assert len(plan.test_groups) == 2
    assert all(group.pin_ids is not None and len(group.pin_ids) == 1 for group in plan.test_groups)
    assert {group.pin_ids[0] for group in plan.test_groups} == set(project.groups[0].pin_ids)


def test_group_bias_is_available_to_signal_and_supply_test_plan_rules() -> None:
    from project_generation import ProjectGenerationDefinition, ProjectGenerationProcessor

    definition = ProjectGenerationDefinition.model_validate(
        {
            "schema_version": "1.0",
            "project": {"name": "Group bias context"},
            "dut": {
                "name": "DUT",
                "pins": {
                    "source": {
                        "type": "inline",
                        "records": [
                            {"designator": "1", "name": "SIG"},
                            {"designator": "2", "name": "SUP"},
                        ],
                    }
                },
            },
            "groups": {
                "explicit": [
                    {
                        "name": "SIGNAL",
                        "group_type": "INPUT",
                        "pins": ["1"],
                        "bias_spec": {"mode": "VOLTAGE", "level": 3.3, "compliance_limit": 0.02},
                    },
                    {
                        "name": "SUPPLY",
                        "group_type": "POWER",
                        "pins": ["2"],
                        "bias_spec": {"mode": "VOLTAGE", "level": 5.0, "compliance_limit": 0.2},
                    },
                ]
            },
            "test_plan_generation": {
                "rules": [
                    {
                        "id": "signal",
                        "groups": {
                            "select": {"where": {"group_type": "INPUT"}},
                            "partition": {"mode": "each"},
                        },
                        "template": {
                            "name": "SIGNAL",
                            "test_type": "SIGNAL",
                            "stress_parameters": {
                                "source_mode": "voltage",
                                "base_level": 0.0,
                                "base_limit": {"from": "group.bias.compliance_limit"},
                                "peak_level": 3.3,
                                "peak_limit": 0.02,
                                "pulse_width": 0.01,
                            },
                        },
                    },
                    {
                        "id": "supply",
                        "groups": {
                            "select": {"where": {"group_type": "POWER"}},
                            "partition": {"mode": "each"},
                        },
                        "template": {
                            "name": "SUPPLY",
                            "test_type": "SUPPLY",
                            "stress_parameters": {
                                "source_mode": "voltage",
                                "base_level": 5.0,
                                "base_limit": {"from": "group.bias.compliance_limit"},
                                "peak_level": 7.5,
                                "peak_limit": 0.2,
                                "pulse_width": 0.01,
                            },
                        },
                    },
                ]
            },
        }
    )

    project = ProjectGenerationProcessor().process(definition)
    signal = next(plan for plan in project.test_plans if plan.test_type == "SIGNAL")
    supply = next(plan for plan in project.test_plans if plan.test_type == "SUPPLY")

    assert signal.test_groups[0].stress_points[0].values["base_limit"] == 0.02
    assert supply.test_groups[0].stress_points[0].values["base_limit"] == 0.2
