import pytest

from project_generation.generation.ganging import (
    NoGangingPolicy,
    SameVoltageGangingPolicy,
    bias_specs_are_compatible,
    get_ganging_policy,
    merge_bias_specs,
)


def test_merge_bias_specs_combines_compatible_partial_specs() -> None:
    assert merge_bias_specs(
        {"level": 3.3},
        {"mode": "VOLTAGE", "level": 3.3},
    ) == {
        "mode": "VOLTAGE",
        "level": 3.3,
    }


def test_merge_bias_specs_rejects_conflicting_fields() -> None:
    with pytest.raises(ValueError, match="conflicting bias field"):
        merge_bias_specs(
            {"mode": "VOLTAGE", "level": 3.3},
            {"mode": "VOLTAGE", "level": 5.0},
        )


def test_bias_specs_are_compatible() -> None:
    assert bias_specs_are_compatible(
        {"level": 3.3},
        {"mode": "VOLTAGE", "level": 3.3},
    )
    assert not bias_specs_are_compatible(
        {"level": 3.3},
        {"level": 5.0},
    )


def test_no_ganging_keeps_every_group_separate() -> None:
    policy = NoGangingPolicy()

    assert policy.gang(
        {
            "POWER_3V3": {"mode": "VOLTAGE", "level": 3.3},
            "INPUT_3V3": {"mode": "VOLTAGE", "level": 3.3},
        }
    ) == (
        ("POWER_3V3",),
        ("INPUT_3V3",),
    )



def test_same_voltage_compatible_accepts_incomplete_compatible_specs() -> None:
    policy = SameVoltageGangingPolicy()

    assert policy.compatible(
        {"level": 3.3},
        {"mode": "VOLTAGE", "level": 3.3},
    )

def test_same_voltage_gangs_compatible_specs() -> None:
    policy = SameVoltageGangingPolicy()

    assert policy.gang(
        {
            "POWER_3V3": {"mode": "VOLTAGE", "level": 3.3},
            "INPUT_3V3": {"mode": "VOLTAGE", "level": 3.3},
            "IO_5V0": {"mode": "VOLTAGE", "level": 5.0},
        }
    ) == (
        ("POWER_3V3", "INPUT_3V3"),
        ("IO_5V0",),
    )


def test_same_voltage_gangs_partial_voltage_specs() -> None:
    policy = SameVoltageGangingPolicy()

    assert policy.gang(
        {
            "POWER_3V3": {"level": 3.3},
            "INPUT_3V3": {"mode": "VOLTAGE", "level": 3.3},
        }
    ) == (("POWER_3V3", "INPUT_3V3"),)


def test_same_voltage_does_not_gang_different_voltage_levels() -> None:
    policy = SameVoltageGangingPolicy()

    assert policy.gang(
        {
            "INPUT_3V3": {"mode": "VOLTAGE", "level": 3.3},
            "INPUT_5V0": {"mode": "VOLTAGE", "level": 5.0},
        }
    ) == (
        ("INPUT_3V3",),
        ("INPUT_5V0",),
    )


def test_same_voltage_does_not_gang_ground_with_voltage() -> None:
    policy = SameVoltageGangingPolicy()

    assert policy.gang(
        {
            "GROUND": {"mode": "GROUND"},
            "INPUT_0V": {"mode": "VOLTAGE", "level": 0.0},
        }
    ) == (
        ("GROUND",),
        ("INPUT_0V",),
    )


def test_same_voltage_gangs_ground_groups_together() -> None:
    policy = SameVoltageGangingPolicy()

    assert policy.gang(
        {
            "GROUND_A": {"mode": "GROUND"},
            "GROUND_B": {"mode": "GROUND"},
        }
    ) == (("GROUND_A", "GROUND_B"),)


def test_merge_bias_specs_uses_largest_compliance_limit() -> None:
    assert merge_bias_specs(
        {"mode": "VOLTAGE", "level": 3.3, "compliance_limit": 0.02},
        {"mode": "VOLTAGE", "level": 3.3, "compliance_limit": 0.2},
    ) == {
        "mode": "VOLTAGE",
        "level": 3.3,
        "compliance_limit": 0.2,
    }


def test_same_voltage_gangs_different_compliance_limits() -> None:
    policy = SameVoltageGangingPolicy()

    assert policy.gang(
        {
            "A": {"mode": "VOLTAGE", "level": 3.3, "compliance_limit": 0.02},
            "B": {"mode": "VOLTAGE", "level": 3.3, "compliance_limit": 0.2},
        }
    ) == (("A", "B"),)


def test_get_ganging_policy_defaults_to_none() -> None:
    assert isinstance(get_ganging_policy(None), NoGangingPolicy)


def test_get_ganging_policy_rejects_unknown_policy() -> None:
    with pytest.raises(ValueError, match='unsupported ganging policy "bogus"'):
        get_ganging_policy("bogus")
