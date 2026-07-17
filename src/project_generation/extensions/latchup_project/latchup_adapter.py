import copy
from dataclasses import dataclass
from typing import Any, Mapping

from project_generation.extensions.latchup_project import dut, latchup_test_plan

from project_generation.diagnostics import ProjectGenerationError
from project_generation.project_processor import GeneratedDeviceState, GeneratedProject


class Bindings:
    Designator = dut.Designator
    DevicePinType = dut.DevicePinType
    DeviceState = latchup_test_plan.DeviceState
    DeviceStateID = latchup_test_plan.DeviceStateID
    Dut = dut.Dut
    LatchUpBiasParameters = latchup_test_plan.LatchUpBiasParameters
    LatchUpPulseParameters = latchup_test_plan.LatchUpPulseParameters
    LatchUpTestPlan = latchup_test_plan.LatchUpTestPlan
    LogicLevelEnum = latchup_test_plan.LogicLevelEnum
    LuTestType = latchup_test_plan.LuTestType
    MatrixAssignment = latchup_test_plan.MatrixAssignment
    Pin = dut.DutPin
    PinGroup = dut.PinGroup
    PinGroupID = dut.PinGroupID
    PinID = dut.PinID
    PolarityEnum = latchup_test_plan.PolarityEnum
    PowerDomain = latchup_test_plan.PowerDomain
    PowerSequence = latchup_test_plan.PowerSequence
    StressParameters = latchup_test_plan.StressParameters
    StressPlan = latchup_test_plan.StressPlan
    TestPlanID = latchup_test_plan.TestPlanID
    TimingInfo = latchup_test_plan.TimingInfo


@dataclass(frozen=True, kw_only=True)
class LatchUpProjectArtifacts:
    dut: Any
    test_plans: tuple[Any, ...]
    device_states: Mapping[str, Any]
    power_sequences: Mapping[str, Any]


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
        sequences = {
            state.name: self._build_power_sequence(state, bindings)
            for state in project.device_states
        }
        plans = tuple(
            self._build_test_plan(plan, project, dut, groups_by_id, states, sequences, bindings)
            for plan in project.test_plans
        )
        return LatchUpProjectArtifacts(
            dut=dut,
            test_plans=plans,
            device_states=states,
            power_sequences=sequences,
        )

    @staticmethod
    def _build_dut(project: GeneratedProject, b: Any) -> Any:
        dut = b.Dut(name=project.dut_name or project.name)
        for pin in project.pins:
            dut.pins.append(
                b.Pin(
                    id=b.PinID(str(pin.id)),
                    designator=b.Designator(pin.designator),
                    pin_name=pin.name,
                    parameters=dict(pin.parameters),
                )
            )
        for group in project.groups:
            try:
                group_type = b.DevicePinType(group.group_type.upper())
            except ValueError as error:
                raise ProjectGenerationError(
                    f'Cannot adapt group type "{group.group_type}" to latchup-project-core',
                    code="adapter.unsupported_group_type",
                    location=f"groups[{group.name}].group_type",
                    owner=group.name,
                ) from error
            dut.add_pin_group(
                b.PinGroup(
                    pin_group_id=b.PinGroupID(str(group.id)),
                    name=group.name,
                    pins=[b.PinID(str(pin_id)) for pin_id in group.pin_ids],
                    group_type=group_type,
                    matrix_assignment=b.MatrixAssignment.FLOAT,
                )
            )
        return dut

    def _build_device_state(self, state: GeneratedDeviceState, dut: Any, groups_by_id: Mapping[Any, Any], b: Any) -> Any:
        result = b.DeviceState(device_state_id=b.DeviceStateID(str(state.id)))
        descriptor_by_id = {group.group_id: group for group in dut.descriptor().test_groups}
        for assignment in state.power_assignments:
            group_id = b.PinGroupID(str(assignment.group_id))
            group = groups_by_id[group_id]
            matrix_assignment = _matrix_assignment(assignment.assignment, b)
            if matrix_assignment == b.MatrixAssignment.GND:
                result.ground_pins.extend(pin for pin in group.pins if pin not in result.ground_pins)
                continue
            if matrix_assignment == b.MatrixAssignment.FLOAT:
                result.floating_pins.extend(pin for pin in group.pins if pin not in result.floating_pins)
                continue
            bias = _bias_parameters(assignment.bias, b)
            result.power_domains.append(
                b.PowerDomain(
                    matrix_assignment=matrix_assignment,
                    test_groups=[descriptor_by_id[group_id]],
                    bias_config=bias,
                )
            )
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
    def _build_test_plan(plan: Any, project: GeneratedProject, dut: Any, groups_by_id: Mapping[Any, Any], states: Mapping[str, Any],
                         sequences: Mapping[str, Any], b: Any) -> Any:
        test_groups = [copy.deepcopy(groups_by_id[b.PinGroupID(str(item.group_id))]) for item in plan.test_groups]
        test_pins = [pin for group in test_groups for pin in group.pins]
        metadata = {
            "generation_rule_id": plan.generation_rule_id,
            "dimensions": dict(plan.dimensions),
            "generated_project": project.name,
        }
        result = b.LatchUpTestPlan(
            test_plan_id=b.TestPlanID(plan.id),
            name=plan.name,
            test_pins=test_pins,
            test_groups=test_groups,
            device_info=dut.descriptor(),
            test_type=_test_type(plan.test_type, b),
            metadata=metadata,
        )
        polarity = plan.dimensions.get("polarity")
        if polarity is not None:
            result.polarity = b.PolarityEnum(str(polarity).lower())
        logic_level = plan.dimensions.get("logic_level")
        if logic_level is not None:
            result.logic_level = b.LogicLevelEnum(str(logic_level).title())
        result.stress_plan = _build_stress_plan(plan, dut, b)
        if plan.device_state:
            result.device_state = copy.deepcopy(states[plan.device_state])
            result.power_sequence = copy.deepcopy(sequences[plan.device_state])
        return result


def _build_stress_plan(plan: Any, dut: Any, b: Any) -> Any | None:
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
    pulse_width = float(values.get("pulse_width", values.get("hold_time", 0.010)))
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

