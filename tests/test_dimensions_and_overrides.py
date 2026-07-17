from conftest import EXAMPLES
from project_generation import GroupRecord, expand_rule, load_project_definition, resolve_group_values


def test_dynamic_dimensions_and_overrides() -> None:
    definition = load_project_definition(EXAMPLES / "customer-current.json")
    rule = definition.test_plan_generation.rules[0]
    groups = [GroupRecord(name="OUT5V5", group_type="OUTPUT", parameters={"v_max": 5.5, "v_min": 0.0})]

    candidates = expand_rule(rule, groups)
    assert len(candidates) == 4

    high_negative = next(
        candidate
        for candidate in candidates
        if candidate.dimensions == {"logic_level": "HIGH", "polarity": "NEGATIVE"}
    )
    assert high_negative.values["device_state"] == "logic_high"
    assert high_negative.values["stress_parameters"]["hold_time"] == 0.075

    group_values = resolve_group_values(high_negative, groups[0], rule.overrides)
    assert group_values["stress_parameters"]["compliance"] == 0.025
