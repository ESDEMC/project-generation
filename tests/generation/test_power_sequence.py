import pytest

from project_generation import ProjectGenerationDefinition, ProjectGenerationError, ProjectGenerationProcessor


def _definition(power_domains: list[dict]) -> ProjectGenerationDefinition:
    group_names = list(dict.fromkeys(group for domain in power_domains for group in domain["groups"]))
    pins = [
        {"designator": str(index), "name": group_name, "parameters": {}}
        for index, group_name in enumerate(group_names, start=1)
    ]
    groups = [
        {"name": group_name, "group_type": "POWER", "pins": [str(index)]}
        for index, group_name in enumerate(group_names, start=1)
    ]
    return ProjectGenerationDefinition.model_validate(
        {
            "schema_version": "1.0",
            "project": {"name": "Power sequence"},
            "dut": {"name": "DUT", "pins": {"source": {"type": "inline", "records": pins}}},
            "groups": {"explicit": groups},
            "power_resources": {"DC2": {"role": "BIAS"}, "DC3": {"role": "BIAS"}},
            "device_states": {"active": {"power_domains": power_domains}},
        }
    )


def test_power_sequence_resolves_dependency_order_and_delays() -> None:
    definition = _definition(
        [
            {
                "name": "logic",
                "groups": ["LOGIC"],
                "assignment": "DC3",
                "bias": {"mode": "VOLTAGE", "level": 5.0},
                "timing": {"power_on": {"delay": 0.005, "after": "supply"}},
            },
            {
                "name": "supply",
                "groups": ["SUPPLY"],
                "assignment": "DC2",
                "bias": {"mode": "VOLTAGE", "level": 28.0},
                "timing": {"power_on": {"delay": 0.002}},
            },
        ]
    )

    state = ProjectGenerationProcessor().process(definition).device_states[0]

    assert [step.domain_name for step in state.power_on_sequence] == ["supply", "logic"]
    assert [step.index for step in state.power_on_sequence] == [0, 1]
    assert state.power_on_sequence[0].delay == 0.002
    assert state.power_on_sequence[0].after is None
    assert state.power_on_sequence[1].delay == 0.005
    assert state.power_on_sequence[1].after == "supply"


def test_power_sequence_preserves_declaration_order_without_dependencies() -> None:
    definition = _definition(
        [
            {"name": "a", "groups": ["A"], "assignment": "DC2", "bias": {"mode": "VOLTAGE", "level": 1.0}},
            {"name": "b", "groups": ["B"], "assignment": "DC3", "bias": {"mode": "VOLTAGE", "level": 2.0}},
        ]
    )

    state = ProjectGenerationProcessor().process(definition).device_states[0]
    assert [step.domain_name for step in state.power_on_sequence] == ["a", "b"]
    assert all(step.delay == 0.0 for step in state.power_on_sequence)


def test_unknown_power_sequence_reference_fails() -> None:
    definition = _definition(
        [
            {
                "name": "logic",
                "groups": ["LOGIC"],
                "assignment": "DC2",
                "bias": {"mode": "VOLTAGE", "level": 5.0},
                "timing": {"power_on": {"after": "missing"}},
            }
        ]
    )

    with pytest.raises(ProjectGenerationError, match='unknown timing domain "missing"'):
        ProjectGenerationProcessor().process(definition)


def test_circular_power_sequence_reference_fails() -> None:
    definition = _definition(
        [
            {
                "name": "a",
                "groups": ["A"],
                "assignment": "DC2",
                "bias": {"mode": "VOLTAGE", "level": 1.0},
                "timing": {"power_on": {"after": "b"}},
            },
            {
                "name": "b",
                "groups": ["B"],
                "assignment": "DC3",
                "bias": {"mode": "VOLTAGE", "level": 2.0},
                "timing": {"power_on": {"after": "a"}},
            },
        ]
    )

    with pytest.raises(ProjectGenerationError, match="circular power-on timing dependency"):
        ProjectGenerationProcessor().process(definition)


def test_power_off_sequence_defaults_to_reverse_power_on_order() -> None:
    definition = _definition(
        [
            {
                "name": "logic",
                "groups": ["LOGIC"],
                "assignment": "DC3",
                "bias": {"mode": "VOLTAGE", "level": 5.0},
                "timing": {"power_on": {"after": "supply"}},
            },
            {
                "name": "supply",
                "groups": ["SUPPLY"],
                "assignment": "DC2",
                "bias": {"mode": "VOLTAGE", "level": 28.0},
            },
        ]
    )

    state = ProjectGenerationProcessor().process(definition).device_states[0]

    assert [step.domain_name for step in state.power_on_sequence] == ["supply", "logic"]
    assert [step.domain_name for step in state.power_off_sequence] == ["logic", "supply"]
    assert state.power_on_sequence == state.power_on_sequence


def test_power_off_sequence_supports_explicit_dependencies_and_delays() -> None:
    definition = _definition(
        [
            {
                "name": "logic",
                "groups": ["LOGIC"],
                "assignment": "DC3",
                "bias": {"mode": "VOLTAGE", "level": 5.0},
                "timing": {"power_off": {"delay": 0.003}},
            },
            {
                "name": "supply",
                "groups": ["SUPPLY"],
                "assignment": "DC2",
                "bias": {"mode": "VOLTAGE", "level": 28.0},
                "timing": {"power_off": {"delay": 0.007, "after": "logic"}},
            },
        ]
    )

    state = ProjectGenerationProcessor().process(definition).device_states[0]

    assert [step.domain_name for step in state.power_off_sequence] == ["logic", "supply"]
    assert [step.delay for step in state.power_off_sequence] == [0.003, 0.007]
    assert state.power_off_sequence[1].after == "logic"


def test_circular_power_off_sequence_reference_fails() -> None:
    definition = _definition(
        [
            {
                "name": "a",
                "groups": ["A"],
                "assignment": "DC2",
                "bias": {"mode": "VOLTAGE", "level": 1.0},
                "timing": {"power_off": {"after": "b"}},
            },
            {
                "name": "b",
                "groups": ["B"],
                "assignment": "DC3",
                "bias": {"mode": "VOLTAGE", "level": 2.0},
                "timing": {"power_off": {"after": "a"}},
            },
        ]
    )

    with pytest.raises(ProjectGenerationError, match="circular power-off timing dependency"):
        ProjectGenerationProcessor().process(definition)
