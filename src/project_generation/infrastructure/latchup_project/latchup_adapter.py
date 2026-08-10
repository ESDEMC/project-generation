import copy
from dataclasses import MISSING, dataclass, fields
from typing import Any, Callable, Mapping, TypeVar
from project_generation.diagnostics import ProjectGenerationError
from project_generation.generation.models import GeneratedDeviceState, GeneratedProject, GeneratedTestPlan
from project_generation.infrastructure.latchup_project.models import dut, latchup_test_plan

T = TypeVar("T")


def _value_or_dataclass_default(
    values: Mapping[str, Any],
    converter: Callable[[Any], T],
    dataclass_type: type[Any],
    field_name: str,
    *candidates: str,
) -> T:
    for candidate in candidates:
        if candidate in values:
            return converter(values[candidate])

    dataclass_field = next(field for field in fields(dataclass_type) if field.name == field_name)
    if dataclass_field.default is not MISSING:
        return converter(dataclass_field.default)
    if dataclass_field.default_factory is not MISSING:
        return converter(dataclass_field.default_factory())

    candidate_names = ", ".join(candidates)
    raise ValueError(
        f'No value provided for "{field_name}" from candidates [{candidate_names}], '
        f"and {dataclass_type.__name__}.{field_name} has no default"
    )


class LatchUpBindings:
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


class LatchUpValueMapper:

    def __init__(self, bindings: LatchUpBindings) -> None:
        self._bindings = bindings

    def matrix_assignment(self, value: str) -> Any:
        normalized = {"GROUND": "GND", "FLOATING": "FLOAT"}.get(value.upper(), value.upper())
        try:
            return self._bindings.MatrixAssignment[normalized]
        except KeyError as error:
            raise ProjectGenerationError(
                f'Cannot adapt power assignment "{value}" to latchup-project-core',
                code="adapter.unsupported_assignment",
                context={"assignment": value},
            ) from error

    def device_pin_type(self, value: str, *, group_name: str) -> Any:
        try:
            return self._bindings.DevicePinType(value.upper())
        except ValueError as error:
            raise ProjectGenerationError(
                f'Cannot adapt group type "{value}" to latchup-project-core',
                code="adapter.unsupported_group_type",
                location=f"groups[{group_name}].group_type",
                owner=group_name,
            ) from error

    def test_type(self, value: str) -> Any:
        normalized = value.strip().upper().replace("-", "_").replace(" ", "_")
        aliases = {"SIGNAL": "SIGNAL_TEST", "SUPPLY": "SUPPLY_TEST", "ITEST": "I_TEST", "ETEST": "E_TEST"}
        normalized = aliases.get(normalized, normalized)
        try:
            return self._bindings.LuTestType[normalized]
        except KeyError as error:
            raise ProjectGenerationError(
                f'Cannot adapt test type "{value}" to latchup-project-core',
                code="adapter.unsupported_test_type",
                context={"test_type": value},
            ) from error

    def polarity(self, value: Any) -> Any:
        return self._bindings.PolarityEnum(str(value).lower())

    def logic_level(self, value: Any) -> Any:
        return self._bindings.LogicLevelEnum(str(value).title())

    def bias_parameters(self, values: Mapping[str, Any]) -> Any | None:
        mode = str(values.get("mode", "")).lower()
        if mode in {"ground", "floating", ""}:
            return None
        level = values.get("level")
        compliance = values.get("compliance_limit", values.get("compliance"))
        if level is None or compliance is None:
            return None
        return self._bindings.LatchUpBiasParameters(
            bias_level=float(level), source_mode=mode, compliance_limit=float(compliance)
        )


class LatchUpDutBuilder:

    def __init__(self, bindings: LatchUpBindings, value_mapper: LatchUpValueMapper) -> None:
        self._bindings = bindings
        self._value_mapper = value_mapper

    def build(self, project: GeneratedProject) -> Any:
        result = self._bindings.Dut(name=project.dut_name or project.name)
        self._add_pins(project, result)
        self._add_pin_groups(project, result)
        return result

    def _add_pins(self, project: GeneratedProject, result: Any) -> None:
        for pin in project.pins:
            parameters = dict(pin.parameters)
            parameters["lu_pin_type"] = parameters.pop("pin_type", None)
            result.pins.append(
                self._bindings.Pin(
                    id=self._bindings.PinID(str(pin.id)),
                    designator=self._bindings.Designator(pin.designator),
                    pin_name=pin.name,
                    parameters=parameters,
                )
            )

    def _add_pin_groups(self, project: GeneratedProject, result: Any) -> None:
        for group in project.groups:
            result.add_pin_group(
                self._bindings.PinGroup(
                    pin_group_id=self._bindings.PinGroupID(str(group.id)),
                    name=group.name,
                    pins=[self._bindings.PinID(str(pin_id)) for pin_id in group.pin_ids],
                    group_type=self._value_mapper.device_pin_type(group.group_type, group_name=group.name),
                    matrix_assignment=self._bindings.MatrixAssignment.FLOAT,
                )
            )


class LatchUpPowerSequenceBuilder:

    def __init__(self, bindings: LatchUpBindings, value_mapper: LatchUpValueMapper) -> None:
        self._bindings = bindings
        self._value_mapper = value_mapper

    def build(self, state: GeneratedDeviceState) -> Any:
        sequence = self._bindings.PowerSequence()
        on_by_assignment = {step.assignment: step for step in state.power_on_sequence}
        off_by_assignment = {step.assignment: step for step in state.power_off_sequence}
        for assignment in self._ordered_assignments(on_by_assignment, off_by_assignment):
            sequence.add_channel(
                self._value_mapper.matrix_assignment(assignment),
                power_on_timing=self._timing_info(on_by_assignment.get(assignment), on_by_assignment),
                power_off_timing=self._timing_info(off_by_assignment.get(assignment), off_by_assignment),
            )
        return sequence

    @staticmethod
    def _ordered_assignments(on_by_assignment: Mapping[str, Any], off_by_assignment: Mapping[str, Any]) -> list[str]:
        assignments = list(on_by_assignment)
        assignments.extend((assignment for assignment in off_by_assignment if assignment not in on_by_assignment))
        return assignments

    def _timing_info(self, step: Any, by_assignment: Mapping[str, Any]) -> Any:
        if step is None:
            return self._bindings.TimingInfo()
        reference = None
        if step.after is not None:
            referenced = self._find_referenced_step(step.after, by_assignment)
            if referenced is not None:
                reference = self._value_mapper.matrix_assignment(referenced.assignment)
        return self._bindings.TimingInfo(delay=step.delay, reference=reference)

    @staticmethod
    def _find_referenced_step(domain_name: str, by_assignment: Mapping[str, Any]) -> Any | None:
        for candidate in by_assignment.values():
            if candidate.domain_name == domain_name:
                return candidate
        return None


class LatchUpDeviceStateBuilder:

    def __init__(
        self,
        bindings: LatchUpBindings,
        value_mapper: LatchUpValueMapper,
        power_sequence_builder: LatchUpPowerSequenceBuilder,
    ) -> None:
        self._bindings = bindings
        self._value_mapper = value_mapper
        self._power_sequence_builder = power_sequence_builder

    def build(self, state: GeneratedDeviceState, dut_object: Any, groups_by_id: Mapping[Any, Any]) -> Any:
        result = self._bindings.DeviceState(device_state_id=self._bindings.DeviceStateID(str(state.id)))
        dut_descriptor = dut_object.descriptor()
        descriptor_by_id = {group.group_id: group for group in dut_descriptor.test_groups}
        for assignment in state.power_assignments:
            self._apply_power_assignment(
                result=result,
                assignment=assignment,
                dut_descriptor=dut_descriptor,
                groups_by_id=groups_by_id,
                descriptor_by_id=descriptor_by_id,
            )
        result.set_power_sequence(self._power_sequence_builder.build(state))
        result.validate()
        return result

    def _apply_power_assignment(
        self,
        *,
        result: Any,
        assignment: Any,
        dut_descriptor: Any,
        groups_by_id: Mapping[Any, Any],
        descriptor_by_id: Mapping[Any, Any],
    ) -> None:
        group_id = self._bindings.PinGroupID(str(assignment.group_id))
        group = groups_by_id[group_id]
        matrix_assignment = self._value_mapper.matrix_assignment(assignment.assignment)
        if matrix_assignment == self._bindings.MatrixAssignment.GND:
            self._extend_unique_pins(result.ground_pins, group.pins, dut_descriptor)
            return
        if matrix_assignment == self._bindings.MatrixAssignment.FLOAT:
            self._extend_unique_pins(result.floating_pins, group.pins, dut_descriptor)
            return
        result.power_domains.append(
            self._bindings.PowerDomain(
                matrix_assignment=matrix_assignment,
                test_groups=[descriptor_by_id[group_id]],
                bias_config=self._value_mapper.bias_parameters(assignment.bias),
            )
        )

    @staticmethod
    def _extend_unique_pins(target: list[Any], pin_ids: list[Any], dut_descriptor: Any) -> None:
        for pin_id in pin_ids:
            pin = dut_descriptor.get_pin(pin_id)
            if pin not in target:
                target.append(pin)


class LatchUpStressParametersBuilder:

    def __init__(self, bindings: LatchUpBindings) -> None:
        self._bindings = bindings

    def build(self, values: Mapping[str, Any], *, plan_name: str, group_name: str) -> Any:
        source_mode = _value_or_dataclass_default(
            values, str, self._bindings.LatchUpPulseParameters, "source_mode", "source_mode"
        ).lower()
        peak = self._required_value(values, "peak", "stress_voltage", "stress_current")
        compliance = self._required_value(values, "compliance_limit", "compliance")
        base = _value_or_dataclass_default(
            values, float, self._bindings.LatchUpPulseParameters, "base", "base", "bias_level"
        )
        compliance_value = float(compliance)
        bias_compliance = self._value_or_fallback(
            values, float, compliance_value, "bias_compliance_limit", "bias_compliance"
        )

        return self._bindings.StressParameters(
            bias_parameters=self._build_bias_parameters(
                values=values, source_mode=source_mode, base=base, bias_compliance=bias_compliance
            ),
            pulse_parameters=self._build_pulse_parameters(
                values=values, source_mode=source_mode, base=base, peak=float(peak), compliance=compliance_value
            ),
            pre_stress_delay=_value_or_dataclass_default(
                values, float, self._bindings.StressParameters, "pre_stress_delay", "pre_stress_delay_s"
            ),
            post_stress_delay=_value_or_dataclass_default(
                values, float, self._bindings.StressParameters, "post_stress_delay", "post_stress_delay_s"
            ),
            measure_duration=_value_or_dataclass_default(
                values, float, self._bindings.StressParameters, "measure_duration", "measure_duration_s"
            ),
        )

    def _build_bias_parameters(
        self, *, values: Mapping[str, Any], source_mode: str, base: float, bias_compliance: float
    ) -> Any:
        bias_level = self._value_or_fallback(values, float, base, "bias_level")
        return self._bindings.LatchUpBiasParameters(
            bias_level=bias_level, source_mode=source_mode, compliance_limit=bias_compliance
        )

    def _build_pulse_parameters(
        self, *, values: Mapping[str, Any], source_mode: str, base: float, peak: float, compliance: float
    ) -> Any:
        return self._bindings.LatchUpPulseParameters(
            base=base,
            peak=peak,
            compliance_limit=compliance,
            source_mode=source_mode,
            pulse_width=_value_or_dataclass_default(
                values, float, self._bindings.LatchUpPulseParameters, "pulse_width", "pulse_width", "hold_time"
            ),
            pulse_delay=_value_or_dataclass_default(
                values, float, self._bindings.LatchUpPulseParameters, "pulse_delay", "pulse_delay"
            ),
        )

    @staticmethod
    def _required_value(values: Mapping[str, Any], *candidates: str) -> Any:
        for candidate in candidates:
            if candidate in values:
                return values[candidate]
        raise ValueError(f'None of the required values were provided: {", ".join(candidates)}')

    @staticmethod
    def _value_or_fallback(
        values: Mapping[str, Any], converter: Callable[[Any], T], fallback: T, *candidates: str
    ) -> T:
        for candidate in candidates:
            if candidate in values:
                return converter(values[candidate])
        return fallback


class LatchUpStressPlanBuilder:

    def __init__(self, bindings: LatchUpBindings, stress_parameters_builder: LatchUpStressParametersBuilder) -> None:
        self._bindings = bindings
        self._stress_parameters_builder = stress_parameters_builder

    def build(self, plan: GeneratedTestPlan, dut_object: Any) -> Any | None:
        descriptor_by_id = {group.group_id: group for group in dut_object.descriptor().test_groups}
        stress_plan = self._bindings.StressPlan()
        for test_group in plan.test_groups:
            if not test_group.stress_points:
                continue
            group_id = self._bindings.PinGroupID(str(test_group.group_id))
            descriptor = descriptor_by_id[group_id]
            parameters = [
                self._stress_parameters_builder.build(
                    point.values, plan_name=plan.name, group_name=test_group.group_name
                )
                for point in test_group.stress_points
            ]
            stress_plan.set_stress_parameters(stress_group=descriptor, stress_parameters=parameters)
        if not stress_plan:
            return None
        return stress_plan


class LatchUpTestPlanBuilder:

    def __init__(
        self,
        bindings: LatchUpBindings,
        value_mapper: LatchUpValueMapper,
        stress_plan_builder: LatchUpStressPlanBuilder,
    ) -> None:
        self._bindings = bindings
        self._value_mapper = value_mapper
        self._stress_plan_builder = stress_plan_builder

    def build(
        self,
        *,
        plan: GeneratedTestPlan,
        project: GeneratedProject,
        dut_object: Any,
        groups_by_id: Mapping[Any, Any],
        states: Mapping[str, Any],
    ) -> Any:
        test_groups = self._copy_test_groups(plan, groups_by_id)
        test_pins = [pin for group in test_groups for pin in group.pins]
        result = self._bindings.LatchUpTestPlan(
            test_plan_id=plan.id,
            name=plan.name,
            test_pins=test_pins,
            test_groups=test_groups,
            device_info=dut_object.descriptor(),
            test_type=self._value_mapper.test_type(plan.test_type),
            metadata=self._build_metadata(plan, project),
        )
        self._apply_dimensions(result, plan)
        self._apply_stress_plan(result, plan, dut_object)
        self._apply_device_state(result, plan, states)
        return result

    def _copy_test_groups(self, plan: GeneratedTestPlan, groups_by_id: Mapping[Any, Any]) -> list[Any]:
        return [copy.deepcopy(groups_by_id[self._bindings.PinGroupID(str(item.group_id))]) for item in plan.test_groups]

    @staticmethod
    def _build_metadata(plan: GeneratedTestPlan, project: GeneratedProject) -> dict[str, Any]:
        return {
            "generation_rule_id": plan.generation_rule_id,
            "dimensions": dict(plan.dimensions),
            "generated_project": project.name,
        }

    def _apply_dimensions(self, result: Any, plan: GeneratedTestPlan) -> None:
        polarity = plan.dimensions.get("polarity")
        if polarity is not None:
            result.polarity = self._value_mapper.polarity(polarity)
        logic_level = plan.dimensions.get("logic_level")
        if logic_level is not None:
            result.logic_level = self._value_mapper.logic_level(logic_level)

    def _apply_stress_plan(self, result: Any, plan: GeneratedTestPlan, dut_object: Any) -> None:
        stress_plan = self._stress_plan_builder.build(plan, dut_object)
        if stress_plan is not None:
            result._stresses = stress_plan.stresses

    @staticmethod
    def _apply_device_state(result: Any, plan: GeneratedTestPlan, states: Mapping[str, Any]) -> None:
        if not plan.device_state:
            return
        result.device_state = copy.deepcopy(states[plan.device_state])
        result.power_sequence = copy.deepcopy(states[plan.device_state].power_sequence())


class LatchUpProjectCoreAdapter:

    def __init__(self, *, bindings: LatchUpBindings | None = None) -> None:
        self._bindings = bindings or LatchUpBindings()
        value_mapper = LatchUpValueMapper(self._bindings)
        power_sequence_builder = LatchUpPowerSequenceBuilder(self._bindings, value_mapper)
        stress_parameters_builder = LatchUpStressParametersBuilder(self._bindings)
        stress_plan_builder = LatchUpStressPlanBuilder(self._bindings, stress_parameters_builder)
        self._dut_builder = LatchUpDutBuilder(self._bindings, value_mapper)
        self._device_state_builder = LatchUpDeviceStateBuilder(self._bindings, value_mapper, power_sequence_builder)
        self._test_plan_builder = LatchUpTestPlanBuilder(self._bindings, value_mapper, stress_plan_builder)

    def build(self, project: GeneratedProject) -> LatchUpProjectArtifacts:
        dut_object = self._dut_builder.build(project)
        groups_by_id = {group.pin_group_id: group for group in dut_object.pin_groups}
        states = {
            state.name: self._device_state_builder.build(state, dut_object, groups_by_id)
            for state in project.device_states
        }
        test_plans = tuple(
            self._test_plan_builder.build(
                plan=plan, project=project, dut_object=dut_object, groups_by_id=groups_by_id, states=states
            )
            for plan in project.test_plans
        )
        return LatchUpProjectArtifacts(dut=dut_object, test_plans=test_plans, device_states=states)


def adapt_to_latchup_project(project: GeneratedProject) -> LatchUpProjectArtifacts:
    return LatchUpProjectCoreAdapter().build(project)
