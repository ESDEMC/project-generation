import pytest

from project_generation.generation.ganging import SameVoltageGangingPolicy, merge_bias_specs


def test_merge_incomplete_bias_specs() -> None:
    assert merge_bias_specs(
        {"level": 3.3},
        {"mode": "VOLTAGE", "level": 3.3},
    ) == {"mode": "VOLTAGE", "level": 3.3}


def test_merge_rejects_conflicting_bias_specs() -> None:
    with pytest.raises(ValueError, match='conflicting bias field "level": 3.3 != 5.0'):
        merge_bias_specs({"level": 3.3}, {"level": 5.0})


def test_same_voltage_gangs_incomplete_compatible_specs() -> None:
    policy = SameVoltageGangingPolicy()
    assert policy.compatible(
        {"level": 3.3},
        {"mode": "VOLTAGE", "level": 3.3},
    )


def test_same_voltage_rejects_different_levels() -> None:
    policy = SameVoltageGangingPolicy()
    assert not policy.compatible({"level": 3.3}, {"level": 5.0})


def test_same_voltage_gangs_ground_together() -> None:
    policy = SameVoltageGangingPolicy()
    assert policy.compatible({"mode": "GROUND"}, {"mode": "GROUND"})
