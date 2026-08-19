from tests.support.paths import DEVICE_STATES_AND_POWER_ALLOCATION, EXAMPLES, EXPLICIT_PROJECT, FIXTURES
import pytest

from project_generation import (
    PowerResourceResolutionError,
    ProjectGenerationError,
    ProjectGenerationDefinition,
    ProjectGenerationProcessor,
)


def test_explicit_power_domains_and_plan_reference_are_resolved() -> None:
    generated = ProjectGenerationProcessor().process(
        ProjectGenerationDefinition.load(EXPLICIT_PROJECT),
        base_directory=EXPLICIT_PROJECT.parent,
    )

    state = generated.device_states[0]
    assert state.name == "logic_high"
    assert [domain.name for domain in state.power_domains] == ["ground", "logic_5v5"]
    assert state.power_domains[1].group_names == ("SU5V5", "IN5V5")
    assert state.power_domains[1].bias == {"mode": "VOLTAGE", "level": 5.5}
    assert generated.test_plans[0].device_state_id == state.id


def test_device_state_rules_resolve_group_references() -> None:
    generated = ProjectGenerationProcessor().process(
        ProjectGenerationDefinition.load(DEVICE_STATES_AND_POWER_ALLOCATION),
        base_directory=DEVICE_STATES_AND_POWER_ALLOCATION.parent,
    )

    state = next(state for state in generated.device_states if state.name == "logic_high")
    by_group = {group.group_name: group.values for group in state.group_states}
    assert by_group["IN5V0"] == {"bias": {"mode": "VOLTAGE", "level": 5.0}}
    assert by_group["SU5V0"] == {"bias": {"mode": "VOLTAGE", "level": 5.0}}
    assert by_group["SU3V3"] == {"bias": {"mode": "VOLTAGE", "level": 3.3}}


def test_device_state_inheritance_merges_group_rules() -> None:
    definition = ProjectGenerationDefinition.model_validate(
        {
            "schema_version": "1.0",
            "project": {"name": "State inheritance"},
            "dut": {
                "name": "DUT",
                "pins": {
                    "source": {
                        "type": "inline",
                        "records": [
                            {"designator": "1", "name": "IN", "parameters": {"pin_type": "INPUT", "v_max": 5.0}}
                        ],
                    }
                },
            },
            "groups": {
                "explicit": [
                    {"name": "IN5V0", "group_type": "INPUT", "pins": ["1"], "parameters": {"v_max": 5.0}}
                ]
            },
            "power_resources": {"DC2": {"role": "BIAS"}},
            "device_states": {
                "base": {
                    "rules": [
                        {
                            "when": {"group.group_type": "INPUT"},
                            "set": {"assignment": "GROUND", "bias": {"mode": "GROUND"}},
                        }
                    ]
                },
                "active": {
                    "extends": "base",
                    "rules": [
                        {
                            "when": {"group.group_type": "INPUT"},
                            "set": {"assignment": "DC2", "bias": {"mode": "VOLTAGE", "level": {"from": "group.v_max"}}},
                        }
                    ],
                },
            },
        }
    )

    generated = ProjectGenerationProcessor().process(definition)
    active = next(state for state in generated.device_states if state.name == "active")
    assert active.extends == "base"
    assert active.group_states[0].values == {"assignment": "DC2", "bias": {"mode": "VOLTAGE", "level": 5.0}}


def test_unknown_plan_device_state_fails() -> None:
    definition = ProjectGenerationDefinition.model_validate(
        {
            "schema_version": "1.0",
            "project": {"name": "Invalid state"},
            "groups": {"external": True},
            "test_plans": [
                {
                    "name": "PLAN",
                    "test_type": "SIGNAL",
                    "device_state": "missing",
                    "test_groups": [],
                }
            ],
        }
    )

    with pytest.raises(ProjectGenerationError, match='unknown device state "missing"'):
        ProjectGenerationProcessor().process(definition)


def _automatic_allocation_definition(*, resource_count: int = 3, mode: str = "automatic") -> ProjectGenerationDefinition:
    resources = {"DC1": {"role": "STRESS"}}
    resources.update({f"DC{index}": {"role": "BIAS"} for index in range(2, resource_count + 1)})
    return ProjectGenerationDefinition.model_validate(
        {
            "schema_version": "1.0",
            "project": {"name": "Automatic allocation"},
            "dut": {
                "name": "DUT",
                "pins": {
                    "source": {
                        "type": "inline",
                        "records": [
                            {"designator": "1", "name": "A", "parameters": {}},
                            {"designator": "2", "name": "B", "parameters": {}},
                        ],
                    }
                },
            },
            "groups": {
                "explicit": [
                    {"name": "A", "group_type": "INPUT", "pins": ["1"]},
                    {"name": "B", "group_type": "OUTPUT", "pins": ["2"]},
                ]
            },
            "power_resources": resources,
            "device_states": {
                "active": {
                    "allocation": {"mode": mode, "strategy": "first_available", "reserve": ["DC1"]},
                    "rules": [
                        {
                            "when": {"group.group_type": {"in": ["INPUT", "OUTPUT"]}},
                            "set": {"bias": {"mode": "VOLTAGE", "level": 3.3}},
                        }
                    ],
                }
            },
        }
    )


def test_automatic_allocation_excludes_stress_and_reserved_resources() -> None:
    generated = ProjectGenerationProcessor().process(_automatic_allocation_definition())
    state = generated.device_states[0]
    by_group = {assignment.group_name: assignment for assignment in state.power_assignments}

    assert by_group["A"].assignment == "DC2"
    assert by_group["B"].assignment == "DC3"
    assert all(assignment.source == "automatic" for assignment in state.power_assignments)


def test_hybrid_allocation_preserves_explicit_assignments() -> None:
    definition = _automatic_allocation_definition(mode="hybrid")
    data = definition.model_dump(by_alias=True)
    data["device_states"]["active"]["rules"].insert(
        0,
        {
            "when": {"group.name": "A"},
            "set": {"assignment": "DC3", "bias": {"mode": "VOLTAGE", "level": 5.0}},
        },
    )

    generated = ProjectGenerationProcessor().process(ProjectGenerationDefinition.model_validate(data))
    state = generated.device_states[0]
    by_group = {assignment.group_name: assignment for assignment in state.power_assignments}

    assert by_group["A"].assignment == "DC3"
    assert by_group["A"].source == "group_rule"
    assert by_group["B"].assignment == "DC2"
    assert by_group["B"].source == "automatic"


def test_automatic_allocation_fails_when_resources_are_insufficient() -> None:
    definition = _automatic_allocation_definition(resource_count=2)

    with pytest.raises(PowerResourceResolutionError) as captured:
        ProjectGenerationProcessor().process(definition)

    error = captured.value
    assert error.code == "hardware.power_resource_unresolved"
    assert error.group_name == "B"
    assert any(
        candidate.resource == "DC2" and candidate.reason == "already assigned to another power domain/group"
        for candidate in error.candidates
    )


def test_same_voltage_ganging_reuses_one_resource() -> None:
    definition = _automatic_allocation_definition(resource_count=2)
    data = definition.model_dump(by_alias=True)
    data["device_states"]["active"]["allocation"]["ganging_policy"] = "same_voltage"

    generated = ProjectGenerationProcessor().process(ProjectGenerationDefinition.model_validate(data))
    state = generated.device_states[0]
    by_group = {assignment.group_name: assignment for assignment in state.power_assignments}

    assert by_group["A"].assignment == "DC2"
    assert by_group["B"].assignment == "DC2"
    assert by_group["A"].source == "automatic"
    assert by_group["B"].source == "ganged:same_voltage"


def test_same_voltage_ganging_does_not_combine_different_biases() -> None:
    definition = _automatic_allocation_definition(resource_count=2)
    data = definition.model_dump(by_alias=True)
    data["device_states"]["active"]["allocation"]["ganging_policy"] = "same_voltage"
    data["device_states"]["active"]["rules"].append(
        {
            "when": {"group.name": "A"},
            "set": {"bias": {"mode": "VOLTAGE", "level": 5.0}},
        }
    )

    with pytest.raises(PowerResourceResolutionError) as captured:
        ProjectGenerationProcessor().process(ProjectGenerationDefinition.model_validate(data))

    assert captured.value.group_name == "B"


def test_same_voltage_ganging_can_reuse_an_explicit_hybrid_assignment() -> None:
    definition = _automatic_allocation_definition(resource_count=3, mode="hybrid")
    data = definition.model_dump(by_alias=True)
    data["device_states"]["active"]["allocation"]["ganging_policy"] = "same_voltage"
    data["device_states"]["active"]["rules"].insert(
        0,
        {
            "when": {"group.name": "A"},
            "set": {"assignment": "DC3", "bias": {"mode": "VOLTAGE", "level": 3.3}},
        },
    )

    generated = ProjectGenerationProcessor().process(ProjectGenerationDefinition.model_validate(data))
    state = generated.device_states[0]
    by_group = {assignment.group_name: assignment for assignment in state.power_assignments}

    assert by_group["A"].assignment == "DC3"
    assert by_group["A"].source == "group_rule"
    assert by_group["B"].assignment == "DC3"
    assert by_group["B"].source == "ganged:same_voltage"


def test_unknown_ganging_policy_fails_clearly() -> None:
    definition = _automatic_allocation_definition()
    data = definition.model_dump(by_alias=True)
    data["device_states"]["active"]["allocation"]["ganging_policy"] = "mystery"

    with pytest.raises(ProjectGenerationError, match='unsupported ganging policy "mystery"'):
        ProjectGenerationProcessor().process(ProjectGenerationDefinition.model_validate(data))


def _hardware_backed_definition(*, level: float = 3.3, assignment: str | None = None) -> ProjectGenerationDefinition:
    rule_set = {"bias": {"mode": "VOLTAGE", "level": level}}
    if assignment is not None:
        rule_set["assignment"] = assignment
    return ProjectGenerationDefinition.model_validate(
        {
            "schema_version": "1.0",
            "project": {"name": "Hardware-backed allocation"},
            "hardware": {"source": "hardware.yaml"},
            "dut": {
                "name": "DUT",
                "pins": {
                    "source": {
                        "type": "inline",
                        "records": [{"designator": "1", "name": "IN", "parameters": {}}],
                    }
                },
            },
            "groups": {
                "explicit": [{"name": "IN", "group_type": "INPUT", "pins": ["1"]}],
            },
            "device_states": {
                "active": {
                    "allocation": {"mode": "automatic", "strategy": "first_available"},
                    "rules": [{"when": {"group.name": "IN"}, "set": rule_set}],
                }
            },
        }
    )


def test_hardware_yaml_supplies_power_resources() -> None:
    definition = _hardware_backed_definition()
    generated = ProjectGenerationProcessor().process(definition, base_directory=FIXTURES)

    assignment = generated.device_states[0].power_assignments[0]
    assert assignment.assignment == "DC2"
    assert assignment.source == "automatic"


def test_automatic_allocation_rejects_hardware_envelope_mismatch() -> None:
    definition = _hardware_backed_definition(level=6.0)

    with pytest.raises(PowerResourceResolutionError) as captured:
        ProjectGenerationProcessor().process(definition, base_directory=FIXTURES)

    error = captured.value
    assert error.code == "hardware.power_resource_unresolved"
    assert error.group_name == "IN"
    assert error.bias == {"mode": "VOLTAGE", "level": 6.0}
    candidates = {candidate.resource: candidate for candidate in error.candidates}
    assert candidates["DC1"].reason == 'role is "STRESS", not "BIAS"'
    assert candidates["DC2"].reason == "requested voltage 6 exceeds hardware maximum 5"
    assert set(candidates) == {"DC1", "DC2"}
    assert "Power resources checked:" in error.format_user_report()
    assert "DC1: rejected" in error.format_user_report()


def test_explicit_assignment_rejects_switch_only_hardware_resource() -> None:
    definition = _hardware_backed_definition(assignment="DC1")
    data = definition.model_dump(by_alias=True)
    data["device_states"]["active"]["allocation"] = {"mode": "hybrid", "strategy": "first_available"}

    with pytest.raises(PowerResourceResolutionError) as captured:
        ProjectGenerationProcessor().process(
            ProjectGenerationDefinition.model_validate(data),
            base_directory=FIXTURES,
        )

    error = captured.value
    assert error.code == "hardware.power_resource_incompatible"
    assert error.requested_resource == "DC1"
    assert error.candidates[0].resource == "DC1"
    assert error.candidates[0].reason == 'hardware connection mode is "switch", not "bias"'
    assert "Requested resource: DC1" in error.format_user_report()


def test_hardware_source_does_not_allow_declaring_nonexistent_resource() -> None:
    definition = _hardware_backed_definition()
    data = definition.model_dump(by_alias=True)
    data["power_resources"] = {"DC9": {"role": "BIAS"}}

    with pytest.raises(ProjectGenerationError, match="DC9"):
        ProjectGenerationProcessor().process(
            ProjectGenerationDefinition.model_validate(data),
            base_directory=FIXTURES,
        )


def test_power_resolution_error_aggregates_multiple_unresolved_groups() -> None:
    definition = _automatic_allocation_definition(resource_count=2)
    data = definition.model_dump(by_alias=True)
    data["dut"]["pins"]["source"]["records"].append(
        {"designator": "3", "name": "C", "parameters": {}}
    )
    data["groups"]["explicit"].append(
        {"name": "C", "group_type": "INPUT", "pins": ["3"]}
    )

    with pytest.raises(PowerResourceResolutionError) as captured:
        ProjectGenerationProcessor().process(ProjectGenerationDefinition.model_validate(data))

    error = captured.value
    assert error.code == "hardware.power_resources_unresolved"
    assert [issue.group_name for issue in error.issues] == ["B", "C"]
    assert all(issue.state_name == "active" for issue in error.issues)
    assert "Configured hardware cannot satisfy 2 device-state power requirements." in error.format_user_report()


def test_hardware_report_identifies_compliance_limit_mismatch() -> None:
    definition = _hardware_backed_definition(level=5.0)
    data = definition.model_dump(by_alias=True)
    data["device_states"]["active"]["rules"][0]["set"]["bias"]["compliance_limit"] = 2.0

    with pytest.raises(PowerResourceResolutionError) as captured:
        ProjectGenerationProcessor().process(
            ProjectGenerationDefinition.model_validate(data),
            base_directory=FIXTURES,
        )

    candidates = {candidate.resource: candidate for candidate in captured.value.candidates}
    assert candidates["DC2"].reason == (
        "requested current compliance 2 exceeds hardware maximum 1 at voltage 5"
    )
