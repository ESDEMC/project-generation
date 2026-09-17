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


def test_relative_series_can_use_absolute_span_as_base() -> None:
    points = expand_stress_parameters(
        {
            "peak": {
                "from_span": ["group.v_max", "group.v_min"],
                "multiply_by": [-0.5, -0.75],
            }
        },
        {"group": {"v_max": 5.0, "v_min": -1.0}},
    )

    assert [point.values["peak"] for point in points] == [-3.0, -4.5]


def test_from_span_requires_two_paths() -> None:
    with pytest.raises(ValueError, match="exactly two paths"):
        expand_stress_parameters(
            {"peak": {"from_span": ["group.v_max"], "multiply_by": [-0.5]}},
            {"group": {"v_max": 5.0, "v_min": 0.0}},
        )


def test_series_length_mismatch_is_rejected() -> None:
    with pytest.raises(ValueError, match="lengths must match"):
        expand_stress_parameters({"voltage": {"values": [1, 2]}, "time": {"values": [1, 2, 3]}}, {})


def test_relative_source_without_operation_uses_source_value_as_is() -> None:
    points = expand_stress_parameters(
        {
            "base": {"from": "group.v_max"},
            "peak": {"from": "group.v_max", "multiply_by": [1.0, 1.5]},
        },
        {"group": {"v_max": 5.0}},
    )

    assert [point.values for point in points] == [
        {"base": 5.0, "peak": 5.0},
        {"base": 5.0, "peak": 7.5},
    ]
