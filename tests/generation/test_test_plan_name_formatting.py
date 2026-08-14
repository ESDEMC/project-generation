from project_generation import (
    ProjectGenerationProcessor,
    load_project_definition,
)
from project_generation.application.workflows import replace_source_paths
from tests.support.paths import REALIS


def test_realis_test_plan_names_use_mapped_dimension_tokens() -> None:
    definition = load_project_definition(REALIS / "generation.yaml")
    input_path = sorted((REALIS / "input").glob("*.json"))[0]
    definition = replace_source_paths(definition, {"realis_project": input_path, "realis_pins": input_path})

    project = ProjectGenerationProcessor().process(definition, base_directory=REALIS)
    signal_plans = [plan for plan in project.test_plans if plan.test_type == "SIGNAL"]
    supply_plans = [plan for plan in project.test_plans if plan.test_type == "SUPPLY"]

    assert signal_plans
    assert supply_plans

    signal_group = signal_plans[0].test_groups[0].group_name
    signal_group_plans = [plan for plan in signal_plans if plan.test_groups[0].group_name == signal_group]
    assert [plan.dimensions for plan in signal_group_plans] == [
        {"polarity": "POSITIVE", "logic_level": "HIGH"},
        {"polarity": "POSITIVE", "logic_level": "LOW"},
        {"polarity": "NEGATIVE", "logic_level": "HIGH"},
        {"polarity": "NEGATIVE", "logic_level": "LOW"},
    ]
    assert [plan.name for plan in signal_group_plans] == [
        f"LU_{signal_group}_H+",
        f"LU_{signal_group}_L+",
        f"LU_{signal_group}_H-",
        f"LU_{signal_group}_L-",
    ]

    supply_group = supply_plans[0].test_groups[0].group_name
    supply_group_plans = [plan for plan in supply_plans if plan.test_groups[0].group_name == supply_group]
    assert [plan.name for plan in supply_group_plans] == [f"LU_{supply_group}_H", f"LU_{supply_group}_L"]
    assert [plan.dimensions for plan in supply_group_plans] == [
        {"logic_level": "HIGH"},
        {"logic_level": "LOW"},
    ]
