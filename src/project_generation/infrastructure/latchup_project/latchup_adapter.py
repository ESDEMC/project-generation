import copy
from dataclasses import dataclass
from typing import Any, Mapping

from project_generation.infrastructure.latchup_project import (
    dut as dut_module,
    latchup_test_plan as latchup_test_plan_module,
)

from project_generation.diagnostics import ProjectGenerationError
from project_generation.generation.models import GeneratedDeviceState, GeneratedProject, GeneratedTestPlan


class Bindings:
    Designator = dut_module.Designator
    DevicePinType = dut_module.DevicePinType
    DeviceState = latchup_test_plan_module.DeviceState
    DeviceStateID = latchup_test_plan_module.DeviceStateID
    Dut = dut_module.Dut
    LatchUpBiasParameters = latchup_test_plan_module.LatchUpBiasParameters
    LatchUpPulseParameters = latchup_test_plan_module.LatchUpPulseParameters
    LatchUpTestPlan = latchup_test_plan_module.LatchUpTestPlan
    LogicLevelEnum = latchup_test_plan_module.LogicLevelEnum
    LuTestType = latchup_test_plan_module.LuTestType
    MatrixAssignment = latchup_test_plan_module.MatrixAssignment
    Pin = dut_module.DutPin
    PinGroup = dut_module.PinGroup
    PinGroupID = dut_module.PinGroupID
    PinID = dut_module.PinID
    PolarityEnum = latchup_test_plan_module.PolarityEnum
    PowerDomain = latchup_test_plan_module.PowerDomain
    PowerSequence = latchup_test_plan_module.PowerSequence
    StressParameters = latchup_test_plan_module.StressParameters
    StressPlan = latchup_test_plan_module.StressPlan
    TestPlanID = latchup_test_plan_module.TestPlanID
    TimingInfo = latchup_test_plan_module.TimingInfo
    TemperatureControl = latchup_test_plan_module.TemperatureControl

TestGroupType = dut_module.SignalTestGroup | dut_module.SupplyTestGroup | dut_module.PinGroup


@dataclass(frozen=True, kw_only=True)
class LatchUpProjectArtifacts:
    dut: Any
    test_plans: tuple[Any, ...]
    device_states: Mapping[str, Any]


class LatchUpProjectCoreAdapter:
    """Adapt a neutral GeneratedProject to latchup-project-core domain objects.

    Imports are intentionally lazy so project-generation remains usable without the
    application domain package installed.
    """

    def build(self, project: GeneratedProject) -> LatchUpProjectArtifacts:
        bindings = Bindings()
        dut = self._build_dut(project, bindings)
        groups_by_id = {group.pin_group_id: group for group in dut.pin_groups}
        states = {
            state.name: self._build_device_state(state, dut, groups_by_id, bindings)
            for state in project.device_states
        }
        plans = tuple(
            self._build_test_plan(
                plan=plan,
                project=project,
                dut=dut,
                groups_by_id=groups_by_id,
                states=states,
                bindings=bindings,
            )
            for plan in project.test_plans
        )
        return LatchUpProjectArtifacts(
            dut=dut,
            test_plans=plans,
            device_states=states,
        )

    @classmethod
    def _build_dut(cls, project: GeneratedProject, bindings: Any) -> Any:
        dut = bindings.Dut(name=project.dut_name or project.name)
        for pin in project.pins:
            pin.parameters["lu_pin_type"] = pin.parameters.pop("pin_type", None)
            dut.pins.append(
                bindings.Pin(
                    id=bindings.PinID(str(pin.id)),
                    designator=bindings.Designator(pin.designator),
                    pin_name=pin.name,
                    parameters=dict(pin.parameters),
                )
            )
        for group in project.groups:
            try:
                group_type = bindings.DevicePinType(group.group_type.upper())
            except ValueError as error:
                raise ProjectGenerationError(
                    f'Cannot adapt group type "{group.group_type}" to latchup-project-core',
                    code="adapter.unsupported_group_type",
                    location=f"groups[{group.name}].group_type",
                    owner=group.name,
                ) from error
            group_type: Bindings.DevicePinType
            group_id = dut.create_pin_group(
                pin_group_id=bindings.PinGroupID(str(group.id)),
                name=group.name,
                pins=[bindings.PinID(str(pin_id)) for pin_id in group.pin_ids],
                group_type=group_type,
                matrix_assignment=bindings.MatrixAssignment.FLOAT,
            )
            pin_group = dut.get_pin_group(group_id)

            cls._apply_parameters(pin_group, copy.deepcopy(dict(group.parameters)))

        return dut

    @staticmethod
    def _apply_parameters(group: TestGroupType, parameters: dict[str, Any]) -> None:
        if "v_max" in parameters:
            group.v_max = parameters.pop("v_max")
        if "v_min" in parameters:
            parameters.pop("v_min")
            group.v_min = 0.0
        for key, value in parameters.items():
            if hasattr(group, key):
                setattr(group, key, value)


    def _build_device_state(self, state: GeneratedDeviceState, dut: Any, groups_by_id: Mapping[Any, Any], bindings: Any) -> Any:
        result = bindings.DeviceState(device_state_id=bindings.DeviceStateID(str(state.id)))
        dut_descriptor = dut.descriptor()
        descriptor_by_id = {group.group_id: group for group in dut_descriptor.test_groups}
        for assignment in state.power_assignments:
            group_id = bindings.PinGroupID(str(assignment.group_id))
            group = groups_by_id[group_id]
            matrix_assignment = _matrix_assignment(assignment.assignment, bindings)
            if matrix_assignment == bindings.MatrixAssignment.GND:
                result.ground_pins.extend(dut_descriptor.get_pin(pin) for pin in group.pins if pin not in result.ground_pins)
                continue
            if matrix_assignment == bindings.MatrixAssignment.FLOAT:
                result.floating_pins.extend(dut_descriptor.get_pin(pin) for pin in group.pins if pin not in result.floating_pins)
                continue
            bias = _bias_parameters(assignment.bias, bindings)
            result.power_domains.append(
                bindings.PowerDomain(
                    matrix_assignment=matrix_assignment,
                    test_groups=[descriptor_by_id[group_id]],
                    bias_config=bias,
                )
            )

        result.set_power_sequence(self._build_power_sequence(state, bindings))

        result.validate()
        return result

    @staticmethod
    def _build_power_sequence(state: GeneratedDeviceState, b: Any) -> Any:
        sequence = b.PowerSequence()
        on_by_assignment = {step.assignment: step for step in state.power_on_sequence}
        off_by_assignment = {step.assignment: step for step in state.power_off_sequence}
        ordered_assignments = list(on_by_assignment)
        ordered_assignments.extend(value for value in off_by_assignment if value not in on_by_assignment)
        for assignment in ordered_assignments:
            on = on_by_assignment.get(assignment)
            off = off_by_assignment.get(assignment)
            sequence.add_channel(
                _matrix_assignment(assignment, b),
                power_on_timing=_timing_info(on, on_by_assignment, b),
                power_off_timing=_timing_info(off, off_by_assignment, b),
            )
        return sequence

    @staticmethod
    def _build_test_plan(
        plan: GeneratedTestPlan,
        project: GeneratedProject,
        dut: Bindings.Dut,
        groups_by_id: Mapping[Any, Any],
        states: Mapping[str, Bindings.DeviceState],
        bindings: Bindings,
    ) -> Bindings.LatchUpTestPlan:
        test_groups = [copy.deepcopy(groups_by_id[bindings.PinGroupID(str(item.group_id))]) for item in plan.test_groups]
        test_pins = [pin for group in test_groups for pin in group.pins]
        metadata = {
            "generation_rule_id": plan.generation_rule_id,
            "dimensions": dict(plan.dimensions),
            "generated_project": project.name,
        }
        result = bindings.LatchUpTestPlan(
            test_plan_id=plan.id,
            name=plan.name,
            test_pins=test_pins,
            test_groups=test_groups,
            device_info=dut.descriptor(),
            test_type=_test_type(plan.test_type, bindings),
            metadata=metadata,
        )
        polarity = plan.dimensions.get("polarity")
        if polarity is not None:
            result.polarity = bindings.PolarityEnum(str(polarity).lower())
        logic_level = plan.dimensions.get("logic_level")
        if logic_level is not None:
            result.logic_level = bindings.LogicLevelEnum(str(logic_level).title())
        if stress_plan := _build_stress_plan(plan, dut, bindings):
            result._stresses = stress_plan.stresses
        if plan.temperature_control is not None:
            temperature = plan.temperature_control
            result.temperature_control = bindings.TemperatureControl(
                enabled=temperature.enabled,
                temperature=temperature.temperature,
                soak_time=temperature.soak_time,
                factor=temperature.factor,
                offset=temperature.offset,
                start_tolerance=temperature.start_tolerance,
                cool_temperature=temperature.cool_temperature,
                timeout=temperature.timeout,
            )
        if plan.device_state:

            result.device_state = copy.deepcopy(states[plan.device_state])
            result.power_sequence = copy.deepcopy(states[plan.device_state].power_sequence())
        return result


def _build_stress_plan(plan: GeneratedTestPlan, dut: Bindings.Dut, b: Bindings) -> Bindings.StressPlan | None:
    descriptor_by_id = {group.group_id: group for group in dut.descriptor().test_groups}
    stress_plan = b.StressPlan()
    for test_group in plan.test_groups:
        if not test_group.stress_points:
            continue
        group_id = b.PinGroupID(test_group.group_id)
        descriptor = descriptor_by_id[group_id]
        parameters = [
            _stress_parameters(point.values, plan_name=plan.name, group_name=test_group.group_name, b=b)
            for point in test_group.stress_points
        ]
        stress_plan.set_stress_parameters(stress_group=descriptor, stress_parameters=parameters)
    return stress_plan if stress_plan else None


def _stress_parameters(values: Mapping[str, Any], *, plan_name: str, group_name: str, b: Any) -> Any:
    source_mode = str(values.get("source_mode", "voltage")).lower()
    peak = values.get("peak", values.get("stress_voltage", values.get("stress_current")))
    compliance = values.get("compliance_limit", values.get("compliance"))
    if peak is None:
        raise ProjectGenerationError(
            f'Stress point for group "{group_name}" in plan "{plan_name}" does not define a stress level',
            code="adapter.missing_stress_level",
            location=f"test_plans[{plan_name}].test_groups[{group_name}].stress_points",
            owner=plan_name,
            context={"group": group_name, "values": dict(values)},
        )
    if compliance is None:
        raise ProjectGenerationError(
            f'Stress point for group "{group_name}" in plan "{plan_name}" does not define compliance',
            code="adapter.missing_stress_compliance",
            location=f"test_plans[{plan_name}].test_groups[{group_name}].stress_points",
            owner=plan_name,
            context={"group": group_name, "values": dict(values)},
        )

    base = float(values.get("base", values.get("bias_level", 0.0)))
    compliance = float(compliance)
    pulse_width_value = values.get("pulse_width", values.get("hold_time"))
    if pulse_width_value is None:
        raise ProjectGenerationError(
            f'Stress point for group "{group_name}" in plan "{plan_name}" does not define pulse_width',
            code="adapter.missing_pulse_width",
            location=f"test_plans[{plan_name}].test_groups[{group_name}].stress_points",
            owner=plan_name,
            context={"group": group_name, "values": dict(values)},
        )
    pulse_width = float(pulse_width_value)
    if pulse_width <= 0:
        raise ProjectGenerationError(
            f'Stress point for group "{group_name}" in plan "{plan_name}" has invalid pulse_width {pulse_width:g}',
            code="adapter.invalid_pulse_width",
            location=f"test_plans[{plan_name}].test_groups[{group_name}].stress_points",
            owner=plan_name,
            context={"group": group_name, "values": dict(values)},
        )
    pulse_delay = float(values.get("pulse_delay", 0.0))
    bias_compliance = float(values.get("bias_compliance_limit", values.get("bias_compliance", compliance)))

    bias_parameters = b.LatchUpBiasParameters(
        bias_level=float(values.get("bias_level", base)),
        source_mode=source_mode,
        compliance_limit=bias_compliance,
    )
    pulse_parameters = b.LatchUpPulseParameters(
        base=base,
        peak=float(peak),
        compliance_limit=compliance,
        source_mode=source_mode,
        pulse_width=pulse_width,
        pulse_delay=pulse_delay,
    )
    return b.StressParameters(
        bias_parameters=bias_parameters,
        pulse_parameters=pulse_parameters,
        pre_stress_delay=float(values.get("pre_stress_delay_s", 0.005)),
        post_stress_delay=float(values.get("post_stress_delay_s", 0.005)),
        measure_duration=float(values.get("measure_duration_s", 0.005)),
    )


def adapt_to_latchup_project(project: GeneratedProject) -> LatchUpProjectArtifacts:
    return LatchUpProjectCoreAdapter().build(project)


def _matrix_assignment(value: str, b: Any) -> Any:
    normalized = {"GROUND": "GND", "FLOATING": "FLOAT"}.get(value.upper(), value.upper())
    try:
        return b.MatrixAssignment[normalized]
    except KeyError as error:
        raise ProjectGenerationError(
            f'Cannot adapt power assignment "{value}" to latchup-project-core',
            code="adapter.unsupported_assignment",
            context={"assignment": value},
        ) from error


def _bias_parameters(values: Mapping[str, Any], b: Any) -> Any | None:
    mode = str(values.get("mode", "")).lower()
    if mode in {"ground", "floating", ""}:
        return None
    level = values.get("level")
    compliance = values.get("compliance_limit", values.get("compliance"))
    if level is None or compliance is None:
        return None
    return b.LatchUpBiasParameters(
        bias_level=float(level),
        source_mode=mode,
        compliance_limit=float(compliance),
    )


def _timing_info(step: Any, by_assignment: Mapping[str, Any], b: Any) -> Any:
    if step is None:
        return b.TimingInfo()
    reference = None
    if step.after is not None:
        referenced = next((candidate for candidate in by_assignment.values() if candidate.domain_name == step.after), None)
        if referenced is not None:
            reference = _matrix_assignment(referenced.assignment, b)
    return b.TimingInfo(delay=step.delay, reference=reference)


def _test_type(value: str, b: Any) -> Any:
    normalized = value.strip().upper().replace("-", "_").replace(" ", "_")
    aliases = {
        "SIGNAL": "SIGNAL_TEST",
        "SUPPLY": "SUPPLY_TEST",
        "ITEST": "I_TEST",
        "ETEST": "E_TEST",
    }
    normalized = aliases.get(normalized, normalized)
    try:
        return b.LuTestType[normalized]
    except KeyError as error:
        raise ProjectGenerationError(
            f'Cannot adapt test type "{value}" to latchup-project-core',
            code="adapter.unsupported_test_type",
            context={"test_type": value},
        ) from error

