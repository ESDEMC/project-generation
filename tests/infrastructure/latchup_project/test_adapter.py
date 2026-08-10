from tests.support.paths import EXPLICIT_PROJECT
import pathlib

import pytest


from project_generation.infrastructure.latchup_project.enums import LogicLevelEnum, LuTestType, MatrixAssignment, PolarityEnum

from project_generation import adapt_to_latchup_project, process_project_definition




@pytest.mark.skip(reason="This test is not yet implemented")
def test_adapter_builds_real_latchup_domain_objects() -> None:
    generated = process_project_definition(EXPLICIT_PROJECT)

    artifacts = adapt_to_latchup_project(generated)

    assert artifacts.dut.name == "Example DUT"
    assert [str(pin.designator) for pin in artifacts.dut.pins] == ["1", "2", "3"]
    assert [group.name for group in artifacts.dut.pin_groups] == ["SU5V5", "IN5V5", "GND"]

    plan = artifacts.test_plans[0]
    assert plan.name == "IN5V5_HIGH_POSITIVE"
    assert plan.test_type is LuTestType.SIGNAL_TEST
    assert plan.polarity is PolarityEnum.POSITIVE
    assert plan.logic_level is LogicLevelEnum.HIGH
    assert [group.name for group in plan.test_groups] == ["IN5V5"]
    assert plan.device_state is not None
    assert plan.power_sequence is not None
    assert plan.device_state.ground_pins
    assert any(domain.matrix_assignment is MatrixAssignment.DC2 for domain in plan.device_state.power_domains)


def test_adapter_builds_real_stress_plan() -> None:
    generated = process_project_definition(EXPLICIT_PROJECT)

    plan = adapt_to_latchup_project(generated).test_plans[0]

    assert plan.stress_plan is not None
    descriptor, parameters = plan.stress_plan.stresses[0]
    assert descriptor.name == "IN5V5"
    assert [item.pulse_parameters.peak for item in parameters] == [5.5, 6.0, 6.5]
    assert [item.pulse_parameters.compliance_limit for item in parameters] == [0.1, 0.1, 0.1]
    assert [item.pulse_parameters.pulse_width for item in parameters] == [0.1, 0.1, 0.1]
    assert all(item.pulse_parameters.base == 0.0 for item in parameters)
    assert all(item.bias_parameters.bias_level == 0.0 for item in parameters)
    assert "generated_stress_points" not in plan.metadata
