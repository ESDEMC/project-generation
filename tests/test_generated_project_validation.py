import uuid

import pytest

from project_generation.diagnostics import ProjectGenerationError
from project_generation.definition.models import ProjectGenerationDefinition
from project_generation.generation.rules import StressPoint
from project_generation.generation.processor import (
    GeneratedDeviceState,
    GeneratedGroup,
    GeneratedGroupState,
    GeneratedPin,
    GeneratedPowerAssignment,
    GeneratedProject,
    GeneratedTestGroup,
    GeneratedTestPlan,
    ValidateGeneratedProjectRequest,
)


def make_definition() -> ProjectGenerationDefinition:
    return ProjectGenerationDefinition.model_validate(
        {
            "schema_version": "1.0",
            "project": {"name": "Test"},
            "power_resources": {"DC1": {"role": "STRESS"}, "DC2": {"role": "BIAS"}},
        }
    )


def make_project() -> GeneratedProject:
    pin_id = uuid.uuid4()
    group_id = uuid.uuid4()
    state_id = uuid.uuid4()
    return GeneratedProject(
        name="Test",
        metadata={},
        dut_name="DUT",
        pins=(GeneratedPin(id=pin_id, designator="1", name="IN", parameters={}),),
        groups=(GeneratedGroup(id=group_id, name="In5V0", group_type="INPUT", pin_ids=(pin_id,), parameters={}),),
        device_states=(
            GeneratedDeviceState(
                id=state_id,
                name="logic_high",
                extends=None,
                allocation={"mode": "hybrid"},
                power_domains=(),
                group_states=(
                    GeneratedGroupState(
                        group_id=group_id,
                        group_name="In5V0",
                        values={"bias": {"mode": "VOLTAGE", "level": 5.0}},
                    ),
                ),
                power_assignments=(
                    GeneratedPowerAssignment(
                        group_id=group_id,
                        group_name="In5V0",
                        assignment="DC2",
                        bias={"mode": "VOLTAGE", "level": 5.0},
                        source="automatic",
                    ),
                ),
                power_on_sequence=(),
                power_off_sequence=(),
            ),
        ),
        test_plans=(
            GeneratedTestPlan(
                id=uuid.uuid4(),
                name="LU_In5V0_POSITIVE_HIGH",
                test_type="SIGNAL",
                dimensions={"logic_level": "HIGH", "polarity": "POSITIVE"},
                device_state="logic_high",
                device_state_id=state_id,
                test_groups=(
                    GeneratedTestGroup(
                        group_id=group_id,
                        group_name="In5V0",
                        stress_points=(StressPoint(values={"source_mode": "voltage", "peak": 5.0}),),
                    ),
                ),
                generation_rule_id="signal_tests",
            ),
        ),
    )


def test_valid_generated_project_passes() -> None:
    ValidateGeneratedProjectRequest(definition=make_definition(), project=make_project()).validate()


def test_group_must_reference_existing_pin() -> None:
    project = make_project()
    bad_group = GeneratedGroup(
        id=project.groups[0].id,
        name=project.groups[0].name,
        group_type=project.groups[0].group_type,
        pin_ids=(uuid.uuid4(),),
        parameters={},
    )
    project = GeneratedProject(**{**project.__dict__, "groups": (bad_group,)})

    with pytest.raises(ProjectGenerationError, match="references unknown pins"):
        ValidateGeneratedProjectRequest(definition=make_definition(), project=project).validate()


def test_floating_assignment_requires_floating_bias() -> None:
    project = make_project()
    state = project.device_states[0]
    bad_assignment = GeneratedPowerAssignment(
        group_id=project.groups[0].id,
        group_name=project.groups[0].name,
        assignment="FLOATING",
        bias={"mode": "VOLTAGE", "level": 5.0},
        source="group_rule",
    )
    bad_state = GeneratedDeviceState(**{**state.__dict__, "power_assignments": (bad_assignment,)})
    project = GeneratedProject(**{**project.__dict__, "device_states": (bad_state,)})

    with pytest.raises(ProjectGenerationError, match="to FLOATING with bias mode"):
        ValidateGeneratedProjectRequest(definition=make_definition(), project=project).validate()


def test_test_plan_state_id_must_match_name() -> None:
    project = make_project()
    plan = project.test_plans[0]
    bad_plan = GeneratedTestPlan(**{**plan.__dict__, "device_state_id": uuid.uuid4()})
    project = GeneratedProject(**{**project.__dict__, "test_plans": (bad_plan,)})

    with pytest.raises(ProjectGenerationError, match="references an invalid device state"):
        ValidateGeneratedProjectRequest(definition=make_definition(), project=project).validate()
