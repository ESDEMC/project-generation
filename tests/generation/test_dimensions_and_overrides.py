from tests.support.paths import STRESS_SERIES_AND_OVERRIDES
from project_generation.generation.rules import (
    GroupRecord,
    expand_rule,
    resolve_group_values,
)
from project_generation import load_project_definition


def test_dynamic_dimensions_and_overrides() -> None:
    definition = load_project_definition(STRESS_SERIES_AND_OVERRIDES)
    rule = definition.test_plan_generation.rules[0]
    groups = [GroupRecord(name="OUT5V5", group_type="OUTPUT", parameters={"v_max": 5.5, "v_min": 0.0})]

    candidates = expand_rule(rule, groups)
    assert len(candidates) == 2

    negative = next(candidate for candidate in candidates if candidate.dimensions == {"polarity": "NEGATIVE"})
    assert negative.values["stress_parameters"]["pulse_width"] == 0.075

    group_values = resolve_group_values(negative, groups[0], rule.overrides)
    assert group_values["stress_parameters"]["compliance"] == 0.025
