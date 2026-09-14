import pytest

from project_generation import (
    PowerResourceResolutionError,
    ProjectGenerationDefinition,
    ProjectGenerationError,
    ProjectGenerationProcessor,
)
from tests.support.paths import FIXTURES


def _definition(
    *,
    a_bias: dict | None = None,
    b_bias: dict | None = None,
    resources: dict | None = None,
    state: dict | None = None,
) -> ProjectGenerationDefinition:
    return ProjectGenerationDefinition.model_validate(
        {
            "schema_version": "1.0",
            "project": {"name": "Device states"},
            "dut": {
                "name": "DUT",
                "pins": {
                    "source": {
                        "type": "inline",
                        "records": [
                            {"designator": "1", "name": "A", "parameters": {"v_max": 3.3}},
                            {"designator": "2", "name": "B", "parameters": {"v_max": 3.3}},
                        ],
                    }
                },
            },
            "groups": {
                "explicit": [
                    {
                        "name": "A",
                        "group_type": "INPUT",
                        "pins": ["1"],
                        "bias_spec": a_bias or {},
                        "parameters": {"v_max": 3.3},
                    },
                    {
                        "name": "B",
                        "group_type": "OUTPUT",
                        "pins": ["2"],
                        "bias_spec": b_bias or {},
                        "parameters": {"v_max": 3.3},
                    },
                ]
            },
            "power_resources": resources
            or {
                "DC1": {"role": "STRESS"},
                "DC2": {"role": "BIAS"},
                "DC3": {"role": "BIAS"},
            },
            "device_states": {"active": state or {}},
        }
    )


def test_group_bias_specs_generate_power_domains() -> None:
    generated = ProjectGenerationProcessor().process(
        _definition(a_bias={"level": 3.3, "compliance_limit": 0.02}, b_bias={"level": 5.0, "compliance_limit": 0.02})
    )
    state = generated.device_states[0]

    assert [(domain.group_names, domain.assignment) for domain in state.power_domains] == [
        (("A",), "DC2"),
        (("B",), "DC3"),
    ]
    assert state.power_domains[0].bias == {"level": 3.3, "mode": "VOLTAGE", "compliance_limit": 0.02}


def test_same_voltage_ganging_creates_one_domain() -> None:
    generated = ProjectGenerationProcessor().process(
        _definition(
            a_bias={"level": 3.3, "compliance_limit": 0.2},
            b_bias={"mode": "VOLTAGE", "level": 3.3, "compliance_limit": 0.02},
            resources={"DC1": {"role": "STRESS"}, "DC2": {"role": "BIAS"}},
            state={"allocation": {"ganging_policy": "same_voltage", "reserve": ["DC1"]}},
        )
    )
    domain = generated.device_states[0].power_domains[0]

    assert domain.group_names == ("A", "B")
    assert domain.assignment == "DC2"
    assert domain.bias == {"level": 3.3, "compliance_limit": 0.2, "mode": "VOLTAGE"}


def test_different_biases_do_not_gang() -> None:
    definition = _definition(
        a_bias={"level": 3.3},
        b_bias={"level": 5.0},
        resources={"DC1": {"role": "STRESS"}, "DC2": {"role": "BIAS"}},
        state={"allocation": {"ganging_policy": "same_voltage", "reserve": ["DC1"]}},
    )

    with pytest.raises(PowerResourceResolutionError):
        ProjectGenerationProcessor().process(definition)


def test_state_rule_modifies_bias_spec_before_ganging() -> None:
    generated = ProjectGenerationProcessor().process(
        _definition(
            a_bias={"level": 3.3},
            b_bias={"level": 3.3},
            state={
                "allocation": {"ganging_policy": "same_voltage"},
                "rules": [
                    {
                        "when": {"group.name": "B"},
                        "set": {"bias_spec.level": 5.0},
                    }
                ],
            },
        )
    )

    assert [domain.bias["level"] for domain in generated.device_states[0].power_domains] == [3.3, 5.0]


def test_state_rule_rejects_non_bias_spec_fields() -> None:
    definition = _definition(
        a_bias={"level": 3.3},
        state={"rules": [{"when": {"group.name": "A"}, "set": {"assignment": "DC2"}}]},
    )

    with pytest.raises(ProjectGenerationError, match="may only set bias_spec"):
        ProjectGenerationProcessor().process(definition)


def test_state_inheritance_carries_effective_bias_specs_then_regangs() -> None:
    definition = _definition(a_bias={"level": 3.3}, b_bias={"level": 3.3})
    data = definition.model_dump(by_alias=True)
    data["device_states"] = {
        "base": {"allocation": {"ganging_policy": "same_voltage"}},
        "child": {
            "extends": "base",
            "allocation": {"ganging_policy": "same_voltage"},
            "rules": [{"when": {"group.name": "B"}, "set": {"bias_spec.level": 5.0}}],
        },
    }

    generated = ProjectGenerationProcessor().process(ProjectGenerationDefinition.model_validate(data))
    base, child = generated.device_states

    assert len(base.power_domains) == 1
    assert len(child.power_domains) == 2


def test_ground_and_floating_do_not_consume_dc_sources() -> None:
    generated = ProjectGenerationProcessor().process(
        _definition(
            a_bias={"mode": "GROUND"},
            b_bias={"mode": "FLOATING"},
            resources={},
            state={"allocation": {"ganging_policy": "same_voltage"}},
        )
    )

    assert [domain.assignment for domain in generated.device_states[0].power_domains] == ["GROUND", "FLOATING"]


def test_unsupported_ganging_policy_fails_clearly() -> None:
    definition = _definition(
        a_bias={"level": 3.3},
        state={"allocation": {"ganging_policy": "mystery"}},
    )

    with pytest.raises(ProjectGenerationError, match='unsupported ganging policy "mystery"'):
        ProjectGenerationProcessor().process(definition)


def test_hardware_envelope_mismatch_reports_resolution_error() -> None:
    definition = ProjectGenerationDefinition.model_validate(
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
                "explicit": [
                    {
                        "name": "IN",
                        "group_type": "INPUT",
                        "pins": ["1"],
                        "bias_spec": {"mode": "VOLTAGE", "level": 6.0, "compliance_limit": 0.02},
                    }
                ]
            },
            "device_states": {"active": {}},
        }
    )

    with pytest.raises(PowerResourceResolutionError) as captured:
        ProjectGenerationProcessor().process(definition, base_directory=FIXTURES)

    assert captured.value.bias == {"mode": "VOLTAGE", "level": 6.0, "compliance_limit": 0.02}


def test_compliance_limit_is_not_inferred_from_group_type() -> None:
    generated = ProjectGenerationProcessor().process(
        _definition(a_bias={"level": 3.3})
    )

    domain = generated.device_states[0].power_domains[0]
    assert domain.bias == {"level": 3.3, "mode": "VOLTAGE"}


def test_ganged_domain_uses_largest_declared_compliance_limit() -> None:
    definition = _definition(
        a_bias={"level": 3.3, "compliance_limit": 0.2},
        b_bias={"level": 3.3, "compliance_limit": 0.02},
        resources={"DC2": {"role": "BIAS"}},
        state={"allocation": {"ganging_policy": "same_voltage"}},
    )

    generated = ProjectGenerationProcessor().process(definition)

    domain = generated.device_states[0].power_domains[0]
    assert domain.group_names == ("A", "B")
    assert domain.bias["compliance_limit"] == pytest.approx(0.2)


def test_state_inheritance_keeps_declared_group_compliance_limits() -> None:
    definition = _definition(
        a_bias={"level": 3.3, "compliance_limit": 0.2},
        b_bias={"level": 3.3, "compliance_limit": 0.02},
        state={},
    )
    data = definition.model_dump(by_alias=True)
    data["device_states"] = {
        "base": {"allocation": {"ganging_policy": "same_voltage"}},
        "child": {
            "extends": "base",
            "allocation": {"ganging_policy": "same_voltage"},
            "rules": [{"when": {"group.name": "B"}, "set": {"bias_spec.level": 5.0}}],
        },
    }

    generated = ProjectGenerationProcessor().process(ProjectGenerationDefinition.model_validate(data))
    child = generated.device_states[1]
    child_domains = {domain.group_names: domain for domain in child.power_domains}

    assert child_domains[("A",)].bias["compliance_limit"] == pytest.approx(0.2)
    assert child_domains[("B",)].bias["compliance_limit"] == pytest.approx(0.02)
