import pytest

from project_generation.generation.rules import (
    expand_stress_parameters,
    generate_range,
)


def test_inclusive_step_range() -> None:
    assert generate_range({"start": 1.0, "stop": 1.3, "step": 0.1}) == [1.0, 1.1, 1.2, 1.3]


def test_num_range() -> None:
    assert generate_range({"start": 5.5, "stop": 7.0, "num": 4}) == [5.5, 6.0, 6.5, 7.0]


def test_relative_factors_and_scalar_broadcast() -> None:
    points = expand_stress_parameters(
        {
            "stress_voltage": {"from": "group.v_max", "multiply_by": [1.0, 1.1, 1.2]},
            "compliance": 0.1,
            "pulse_width": 0.05,
        },
        {"group": {"v_max": 5.0}},
    )
    assert [point.values for point in points] == [
        {"stress_voltage": 5.0, "compliance": 0.1, "pulse_width": 0.05},
        {"stress_voltage": 5.5, "compliance": 0.1, "pulse_width": 0.05},
        {"stress_voltage": 6.0, "compliance": 0.1, "pulse_width": 0.05},
    ]


def test_series_length_mismatch_is_rejected() -> None:
    with pytest.raises(ValueError, match="lengths must match"):
        expand_stress_parameters({"voltage": {"values": [1, 2]}, "time": {"values": [1, 2, 3]}}, {})
