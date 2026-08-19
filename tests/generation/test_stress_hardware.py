from pathlib import Path

import pytest

from project_generation import ProjectGenerationDefinition, ProjectGenerationProcessor, StressSupplyResolutionError


def _definition() -> ProjectGenerationDefinition:
    return ProjectGenerationDefinition.model_validate(
        {
            "schema_version": "1.0",
            "project": {"name": "Stress hardware"},
            "hardware": {"source": "hardware.yaml"},
            "dut": {
                "name": "DUT",
                "pins": {"source": {"type": "inline", "records": [{"designator": "1", "name": "IN"}]}},
            },
            "groups": {"explicit": [{"name": "IN", "group_type": "INPUT", "pins": ["1"]}]},
            "test_plans": [
                {
                    "name": "LU_IN",
                    "test_type": "SIGNAL",
                    "test_groups": [
                        {
                            "group": "IN",
                            "stress_points": [
                                {
                                    "source_mode": "voltage",
                                    "base": 5.0,
                                    "peak": 30.0,
                                    "compliance": 0.5,
                                    "pulse_width": 0.01,
                                }
                            ],
                        }
                    ],
                }
            ],
        }
    )


def _write_hardware(
    path: Path,
    *,
    dc_voltage: float = 20.0,
    pulse_voltage: float = 100.0,
    pulse_current: float = 1.0,
    min_pulse_width: float = 0.0002,
    max_pulse_width: float = 0.1,
) -> None:
    path.write_text(
        f'''power_supply:\n  hardware_connections:\n    - channel:\n        power_supply_id: switch-source\n        channel_id: switch-channel\n      matrix_assignment: DC1\n      mode: switch\nmetadata:\n  power_supply:\n    - matrix_assignment: DC1\n      name: Source Switch\n      power_envelopes:\n        DC:\n          - max_voltage: {dc_voltage}\n            max_current: 1.0\n        PULSE:\n          - max_peak_voltage: {pulse_voltage}\n            max_base_voltage: 0.0\n            max_peak_current: {pulse_current}\n            max_base_current: 0.0\n            min_pulse_width: {min_pulse_width}\n            max_pulse_width: {max_pulse_width}\n            max_duty_cycle: 1.0\n''',
        encoding="utf-8",
    )


def test_source_switch_uses_dc_for_bias_and_pulse_for_stress(tmp_path: Path) -> None:
    _write_hardware(tmp_path / "hardware.yaml")
    project = ProjectGenerationProcessor().process(_definition(), base_directory=tmp_path)

    assert project.test_plans[0].stress_supply is not None
    assert project.test_plans[0].stress_supply.resource == "DC1"
    assert project.test_plans[0].stress_supply.strategy == "source_switch"


def test_source_switch_rejects_pre_post_bias_outside_dc_envelope(tmp_path: Path) -> None:
    _write_hardware(tmp_path / "hardware.yaml", dc_voltage=4.0)

    with pytest.raises(StressSupplyResolutionError) as captured:
        ProjectGenerationProcessor().process(_definition(), base_directory=tmp_path)

    candidate = captured.value.issues[0].candidates[0]
    assert candidate.reason == "pre/post bias: requested voltage 5 exceeds DC maximum 4"
    assert "pre/post bias" in captured.value.format_user_report()


def test_source_switch_rejects_peak_outside_pulse_envelope(tmp_path: Path) -> None:
    _write_hardware(tmp_path / "hardware.yaml", pulse_voltage=20.0)

    with pytest.raises(StressSupplyResolutionError) as captured:
        ProjectGenerationProcessor().process(_definition(), base_directory=tmp_path)

    candidate = captured.value.issues[0].candidates[0]
    assert candidate.reason == "stress pulse: requested peak voltage 30 exceeds PULSE maximum 20"
    assert captured.value.context["issues"][0]["stress"]["peak"] == 30.0


def test_biased_pulse_requires_pulse_width(tmp_path: Path) -> None:
    definition = _definition()
    definition.test_plans[0].test_groups[0].stress_points[0].pop("pulse_width")
    _write_hardware(tmp_path / "hardware.yaml")

    with pytest.raises(Exception) as captured:
        ProjectGenerationProcessor().process(definition, base_directory=tmp_path)

    assert "invalid biased-pulse stress point" in str(captured.value)


def test_legacy_hold_time_is_accepted_at_input_boundary(tmp_path: Path) -> None:
    definition = _definition()
    stress_point = definition.test_plans[0].test_groups[0].stress_points[0]
    stress_point["hold_time"] = stress_point.pop("pulse_width")
    _write_hardware(tmp_path / "hardware.yaml")

    project = ProjectGenerationProcessor().process(definition, base_directory=tmp_path)

    assert project.test_plans[0].stress_supply is not None


def test_source_switch_rejects_pulse_width_below_pulse_envelope(tmp_path: Path) -> None:
    definition = _definition()
    definition.test_plans[0].test_groups[0].stress_points[0]["pulse_width"] = 0.0001
    _write_hardware(tmp_path / "hardware.yaml")

    with pytest.raises(StressSupplyResolutionError) as captured:
        ProjectGenerationProcessor().process(definition, base_directory=tmp_path)

    assert captured.value.issues[0].candidates[0].reason == (
        "stress pulse: requested pulse width 0.0001 is below PULSE minimum 0.0002"
    )


def test_source_switch_rejects_pulse_width_above_pulse_envelope(tmp_path: Path) -> None:
    definition = _definition()
    definition.test_plans[0].test_groups[0].stress_points[0]["pulse_width"] = 0.2
    _write_hardware(tmp_path / "hardware.yaml", max_pulse_width=0.1)

    with pytest.raises(StressSupplyResolutionError) as captured:
        ProjectGenerationProcessor().process(definition, base_directory=tmp_path)

    assert captured.value.issues[0].candidates[0].reason == (
        "stress pulse: requested pulse width 0.2 exceeds PULSE maximum 0.1"
    )


def test_source_switch_requires_one_pulse_envelope_to_support_whole_requirement(tmp_path: Path) -> None:
    definition = _definition()
    point = definition.test_plans[0].test_groups[0].stress_points[0]
    point.update({"peak": 200.0, "compliance": 1.0, "pulse_width": 0.01})
    path = tmp_path / "hardware.yaml"
    path.write_text(
        """power_supply:
  hardware_connections:
    - channel:
        power_supply_id: switch-source
        channel_id: switch-channel
      matrix_assignment: DC1
      mode: switch
metadata:
  power_supply:
    - matrix_assignment: DC1
      name: Source Switch
      power_envelopes:
        DC:
          - max_voltage: 20
            max_current: 1
        PULSE:
          - max_peak_voltage: 300
            max_peak_current: 1
            min_pulse_width: 0.0002
            max_pulse_width: 0.005
          - max_peak_voltage: 100
            max_peak_current: 1
            min_pulse_width: 0.0002
            max_pulse_width: 0.1
""",
        encoding="utf-8",
    )

    with pytest.raises(StressSupplyResolutionError) as captured:
        ProjectGenerationProcessor().process(definition, base_directory=tmp_path)

    assert captured.value.issues[0].candidates[0].reason == (
        "stress pulse: no PULSE power envelope supports peak voltage 200 with current compliance 1 and pulse width 0.01"
    )


def test_new_hardware_example_resolves_real_source_switch_pulse_ranges() -> None:
    example = Path(__file__).parents[2] / "examples" / "sources" / "hardware_config"
    project = ProjectGenerationProcessor().process(_definition(), base_directory=example)

    assert project.test_plans[0].stress_supply is not None
    assert project.test_plans[0].stress_supply.resource == "DC1"


def test_real_hardware_rejects_requirement_split_across_pulse_ranges() -> None:
    definition = _definition()
    point = definition.test_plans[0].test_groups[0].stress_points[0]
    point.update({"peak": 200.0, "compliance": 1.0, "pulse_width": 0.01})
    example = Path(__file__).parents[2] / "examples" / "sources" / "hardware_config"

    with pytest.raises(StressSupplyResolutionError) as captured:
        ProjectGenerationProcessor().process(definition, base_directory=example)

    reason = captured.value.issues[0].candidates[0].reason
    assert reason == (
        "stress pulse: no PULSE power envelope supports peak voltage 200 with current compliance 1 and pulse width 0.01"
    )


def test_real_hardware_rejects_pulse_below_200_microseconds() -> None:
    definition = _definition()
    definition.test_plans[0].test_groups[0].stress_points[0]["pulse_width"] = 0.0001
    example = Path(__file__).parents[2] / "examples" / "sources" / "hardware_config"

    with pytest.raises(StressSupplyResolutionError) as captured:
        ProjectGenerationProcessor().process(definition, base_directory=example)

    reason = captured.value.issues[0].candidates[0].reason
    assert "pulse width 0.0001" in reason
    assert "PULSE" in reason
