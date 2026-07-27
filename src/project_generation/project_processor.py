import csv
import json
import math
import pathlib
import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from project_generation.diagnostics import ProjectGenerationError
from project_generation.ganging import ExistingPowerAssignment, GangingCandidate, get_ganging_policy
from project_generation.models import (
    CsvSource,
    DutDefinition,
    ExcelSource,
    ExplicitGroupDefinition,
    ExplicitTestPlanDefinition,
    FormatterDefinition,
    GroupGenerationRule,
    InlineSource,
    JsonSource,
    ProjectGenerationDefinition,
    SourceDefinition,
    SourceFieldMapping,
    TestPlanRuleDefinition,
)
from project_generation.processing import (
    GroupRecord,
    StressPoint,
    candidate_context,
    expand_rule,
    expand_stress_parameters,
    matches,
    resolve_group_values_and_exclusion,
    resolve_path,
)

_PROJECT_GENERATION_NAMESPACE = uuid.UUID("b5cc252e-8608-4e8c-a03f-8ce6e5f55b43")
_TEMPLATE_FIELD = re.compile(r"\{([^{}]+)}")


@dataclass(frozen=True, kw_only=True)
class GeneratedPin:
    id: uuid.UUID
    designator: str
    name: str
    parameters: dict[str, Any] = field(default_factory=dict)

    def context(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "designator": self.designator,
            "name": self.name,
            "parameters": dict(self.parameters),
        }


@dataclass(frozen=True, kw_only=True)
class GeneratedGroup:
    id: uuid.UUID
    name: str
    group_type: str
    pin_ids: tuple[uuid.UUID, ...]
    parameters: Mapping[str, Any] = field(default_factory=dict)
    generation_rule_id: str | None = None

    def context(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "name": self.name,
            "group_type": self.group_type,
            "parameters": dict(self.parameters),
        }

    def as_group_record(self) -> GroupRecord:
        return GroupRecord(name=self.name, group_type=self.group_type, parameters=self.parameters)


@dataclass(frozen=True, kw_only=True)
class GeneratedPowerDomain:
    name: str
    group_ids: tuple[uuid.UUID, ...]
    group_names: tuple[str, ...]
    assignment: str
    bias: Mapping[str, Any]
    timing: Mapping[str, Any] | None = None


@dataclass(frozen=True, kw_only=True)
class GeneratedGroupState:
    group_id: uuid.UUID
    group_name: str
    values: Mapping[str, Any]


@dataclass(frozen=True, kw_only=True)
class GeneratedPowerAssignment:
    group_id: uuid.UUID
    group_name: str
    assignment: str
    bias: Mapping[str, Any]
    source: str


@dataclass(frozen=True, kw_only=True)
class GeneratedPowerSequenceStep:
    index: int
    domain_name: str
    assignment: str
    group_ids: tuple[uuid.UUID, ...]
    group_names: tuple[str, ...]
    bias: Mapping[str, Any]
    delay: float
    after: str | None


@dataclass(frozen=True, kw_only=True)
class GeneratedDeviceState:
    id: uuid.UUID
    name: str
    extends: str | None
    allocation: Mapping[str, Any] | None
    power_domains: tuple[GeneratedPowerDomain, ...]
    group_states: tuple[GeneratedGroupState, ...]
    power_assignments: tuple[GeneratedPowerAssignment, ...]
    power_on_sequence: tuple[GeneratedPowerSequenceStep, ...]
    power_off_sequence: tuple[GeneratedPowerSequenceStep, ...]


@dataclass(frozen=True, kw_only=True)
class GeneratedTestGroup:
    group_id: uuid.UUID
    group_name: str
    stress_points: tuple[StressPoint, ...]


@dataclass(frozen=True, kw_only=True)
class GeneratedTestPlan:
    id: uuid.UUID
    name: str
    test_type: str
    dimensions: Mapping[str, Any]
    device_state: str | None
    device_state_id: uuid.UUID | None
    test_groups: tuple[GeneratedTestGroup, ...]
    generation_rule_id: str | None = None


@dataclass(frozen=True, kw_only=True)
class GeneratedProject:
    name: str
    metadata: Mapping[str, Any]
    dut_name: str | None
    pins: tuple[GeneratedPin, ...]
    groups: tuple[GeneratedGroup, ...]
    device_states: tuple[GeneratedDeviceState, ...]
    test_plans: tuple[GeneratedTestPlan, ...]


@dataclass(frozen=True, kw_only=True)
class GenerateTestPlansRequest:
    definition: ProjectGenerationDefinition
    groups: tuple[GeneratedGroup, ...]
    device_states: tuple[GeneratedDeviceState, ...]

    def validate(self) -> None:
        group_names = [group.name for group in self.groups]
        duplicate_group_names = sorted({name for name in group_names if group_names.count(name) > 1})
        if duplicate_group_names:
            raise ProjectGenerationError(
                f"Duplicate generated group names: {', '.join(duplicate_group_names)}",
                code="test_plan.duplicate_groups",
                location="groups",
            )

        state_names = [state.name for state in self.device_states]
        duplicate_state_names = sorted({name for name in state_names if state_names.count(name) > 1})
        if duplicate_state_names:
            raise ProjectGenerationError(
                f"Duplicate generated device-state names: {', '.join(duplicate_state_names)}",
                code="test_plan.duplicate_device_states",
                location="device_states",
            )

        for rule in self.definition.test_plan_generation.rules:
            selected = [
                group
                for group in self.groups
                if matches(
                    rule.groups.select.where,
                    {"group": group.as_group_record().context(), **group.as_group_record().context()},
                )
            ]
            if not selected:
                raise ProjectGenerationError(
                    f'Test plan rule "{rule.id}" did not select any groups',
                    code="test_plan.no_selected_groups",
                    location=f"test_plan_generation.rules.{rule.id}.groups.select",
                    owner=rule.id,
                )


@dataclass(frozen=True, kw_only=True)
class ValidateGeneratedProjectRequest:
    definition: ProjectGenerationDefinition
    project: GeneratedProject

    def validate(self) -> None:
        self._validate_unique_identity()
        self._validate_group_membership()
        self._validate_device_states()
        self._validate_test_plans()

    def _validate_unique_identity(self) -> None:
        self._require_unique((pin.id for pin in self.project.pins), "pin IDs", "generated_project.pins")
        self._require_unique((pin.designator for pin in self.project.pins), "pin designators", "generated_project.pins")
        self._require_unique((group.id for group in self.project.groups), "group IDs", "generated_project.groups")
        self._require_unique((group.name for group in self.project.groups), "group names", "generated_project.groups")
        self._require_unique((state.id for state in self.project.device_states), "device-state IDs", "generated_project.device_states")
        self._require_unique((state.name for state in self.project.device_states), "device-state names", "generated_project.device_states")
        self._require_unique((plan.id for plan in self.project.test_plans), "test-plan IDs", "generated_project.test_plans")
        self._require_unique((plan.name for plan in self.project.test_plans), "test-plan names", "generated_project.test_plans")

    @staticmethod
    def _require_unique(values: Iterable[Any], label: str, location: str) -> None:
        values = list(values)
        duplicates = sorted({str(value) for value in values if values.count(value) > 1})
        if duplicates:
            raise ProjectGenerationError(
                f"Generated project contains duplicate {label}: {', '.join(duplicates)}",
                code="generated_project.duplicate_identity",
                location=location,
                context={"duplicates": duplicates},
            )

    def _validate_group_membership(self) -> None:
        pin_ids = {pin.id for pin in self.project.pins}
        for group in self.project.groups:
            if not group.pin_ids:
                raise ProjectGenerationError(
                    f'Generated group "{group.name}" does not contain any pins',
                    code="generated_project.empty_group",
                    location=f"generated_project.groups.{group.name}",
                    owner=group.name,
                )
            missing = [str(pin_id) for pin_id in group.pin_ids if pin_id not in pin_ids]
            if missing:
                raise ProjectGenerationError(
                    f'Generated group "{group.name}" references unknown pins',
                    code="generated_project.unknown_group_pins",
                    location=f"generated_project.groups.{group.name}.pin_ids",
                    owner=group.name,
                    context={"pin_ids": missing},
                )

    def _validate_device_states(self) -> None:
        groups_by_id = {group.id: group for group in self.project.groups}
        groups_by_name = {group.name: group for group in self.project.groups}
        resources = set(self.definition.power_resources)
        pseudo_resources = {"GROUND", "FLOATING"}

        for state in self.project.device_states:
            assignment_by_group: dict[str, GeneratedPowerAssignment] = {}
            for assignment in state.power_assignments:
                group = groups_by_id.get(assignment.group_id)
                if group is None or group.name != assignment.group_name:
                    raise ProjectGenerationError(
                        f'Device state "{state.name}" has a power assignment for an unknown group',
                        code="generated_project.invalid_power_assignment_group",
                        location=f"generated_project.device_states.{state.name}.power_assignments",
                        owner=state.name,
                        context={"group_name": assignment.group_name, "group_id": str(assignment.group_id)},
                    )
                if assignment.group_name in assignment_by_group:
                    raise ProjectGenerationError(
                        f'Device state "{state.name}" assigns group "{assignment.group_name}" more than once',
                        code="generated_project.duplicate_power_assignment",
                        location=f"generated_project.device_states.{state.name}.power_assignments",
                        owner=state.name,
                        context={"group_name": assignment.group_name},
                    )
                if assignment.assignment not in resources | pseudo_resources:
                    raise ProjectGenerationError(
                        f'Device state "{state.name}" uses unknown power resource "{assignment.assignment}"',
                        code="generated_project.unknown_power_resource",
                        location=f"generated_project.device_states.{state.name}.power_assignments",
                        owner=state.name,
                    )
                self._validate_assignment_bias(state.name, assignment.group_name, assignment.assignment, assignment.bias)
                assignment_by_group[assignment.group_name] = assignment

            for group_state in state.group_states:
                group = groups_by_id.get(group_state.group_id)
                if group is None or group.name != group_state.group_name:
                    raise ProjectGenerationError(
                        f'Device state "{state.name}" contains values for an unknown group',
                        code="generated_project.invalid_group_state",
                        location=f"generated_project.device_states.{state.name}.group_states",
                        owner=state.name,
                        context={"group_name": group_state.group_name, "group_id": str(group_state.group_id)},
                    )
                if "bias" in group_state.values and group_state.group_name not in assignment_by_group:
                    raise ProjectGenerationError(
                        f'Device state "{state.name}" has a biased group without a resolved assignment: {group_state.group_name}',
                        code="generated_project.unassigned_biased_group",
                        location=f"generated_project.device_states.{state.name}.group_states.{group_state.group_name}",
                        owner=state.name,
                    )

            for domain in state.power_domains:
                if len(domain.group_ids) != len(domain.group_names):
                    raise ProjectGenerationError(
                        f'Device state "{state.name}" power domain "{domain.name}" has mismatched group IDs and names',
                        code="generated_project.invalid_power_domain",
                        location=f"generated_project.device_states.{state.name}.power_domains.{domain.name}",
                        owner=state.name,
                    )
                for group_id, group_name in zip(domain.group_ids, domain.group_names, strict=True):
                    group = groups_by_id.get(group_id)
                    if group is None or group.name != group_name or group_name not in groups_by_name:
                        raise ProjectGenerationError(
                            f'Device state "{state.name}" power domain "{domain.name}" references an unknown group',
                            code="generated_project.invalid_power_domain_group",
                            location=f"generated_project.device_states.{state.name}.power_domains.{domain.name}",
                            owner=state.name,
                            context={"group_name": group_name, "group_id": str(group_id)},
                        )

    @staticmethod
    def _validate_assignment_bias(state_name: str, group_name: str, assignment: str, bias: Mapping[str, Any]) -> None:
        mode = str(bias.get("mode", "")).upper()
        if assignment == "GROUND" and mode != "GROUND":
            raise ProjectGenerationError(
                f'Device state "{state_name}" assigns group "{group_name}" to GROUND with bias mode "{mode or "<missing>"}"',
                code="generated_project.inconsistent_ground_bias",
                location=f"generated_project.device_states.{state_name}.power_assignments.{group_name}",
                owner=state_name,
            )
        if assignment == "FLOATING" and mode != "FLOATING":
            raise ProjectGenerationError(
                f'Device state "{state_name}" assigns group "{group_name}" to FLOATING with bias mode "{mode or "<missing>"}"',
                code="generated_project.inconsistent_floating_bias",
                location=f"generated_project.device_states.{state_name}.power_assignments.{group_name}",
                owner=state_name,
            )

    def _validate_test_plans(self) -> None:
        groups_by_id = {group.id: group for group in self.project.groups}
        states_by_id = {state.id: state for state in self.project.device_states}
        states_by_name = {state.name: state for state in self.project.device_states}

        for plan in self.project.test_plans:
            if not plan.test_groups:
                raise ProjectGenerationError(
                    f'Test plan "{plan.name}" does not contain any test groups',
                    code="generated_project.empty_test_plan",
                    location=f"generated_project.test_plans.{plan.name}",
                    owner=plan.name,
                )
            if plan.device_state is None:
                if plan.device_state_id is not None:
                    raise ProjectGenerationError(
                        f'Test plan "{plan.name}" has a device-state ID without a device-state name',
                        code="generated_project.invalid_test_plan_state",
                        location=f"generated_project.test_plans.{plan.name}.device_state",
                        owner=plan.name,
                    )
            else:
                state = states_by_name.get(plan.device_state)
                if state is None or plan.device_state_id != state.id or plan.device_state_id not in states_by_id:
                    raise ProjectGenerationError(
                        f'Test plan "{plan.name}" references an invalid device state "{plan.device_state}"',
                        code="generated_project.invalid_test_plan_state",
                        location=f"generated_project.test_plans.{plan.name}.device_state",
                        owner=plan.name,
                    )

            seen_groups: set[uuid.UUID] = set()
            for test_group in plan.test_groups:
                group = groups_by_id.get(test_group.group_id)
                if group is None or group.name != test_group.group_name:
                    raise ProjectGenerationError(
                        f'Test plan "{plan.name}" references an unknown group "{test_group.group_name}"',
                        code="generated_project.invalid_test_group",
                        location=f"generated_project.test_plans.{plan.name}.test_groups",
                        owner=plan.name,
                    )
                if test_group.group_id in seen_groups:
                    raise ProjectGenerationError(
                        f'Test plan "{plan.name}" contains duplicate test group "{test_group.group_name}"',
                        code="generated_project.duplicate_test_group",
                        location=f"generated_project.test_plans.{plan.name}.test_groups",
                        owner=plan.name,
                    )
                seen_groups.add(test_group.group_id)
                if not test_group.stress_points:
                    raise ProjectGenerationError(
                        f'Test plan "{plan.name}" group "{test_group.group_name}" does not contain stress points',
                        code="generated_project.empty_stress_points",
                        location=f"generated_project.test_plans.{plan.name}.test_groups.{test_group.group_name}",
                        owner=plan.name,
                    )
                for index, stress_point in enumerate(test_group.stress_points):
                    self._validate_stress_point(plan.name, test_group.group_name, index, stress_point)

    @staticmethod
    def _validate_stress_point(plan_name: str, group_name: str, index: int, stress_point: StressPoint) -> None:
        if not stress_point.values:
            raise ProjectGenerationError(
                f'Test plan "{plan_name}" group "{group_name}" has an empty stress point',
                code="generated_project.empty_stress_point",
                location=f"generated_project.test_plans.{plan_name}.test_groups.{group_name}.stress_points[{index}]",
                owner=plan_name,
            )
        for name, value in stress_point.values.items():
            if isinstance(value, float) and not math.isfinite(value):
                raise ProjectGenerationError(
                    f'Test plan "{plan_name}" group "{group_name}" has a non-finite stress parameter "{name}"',
                    code="generated_project.invalid_stress_value",
                    location=f"generated_project.test_plans.{plan_name}.test_groups.{group_name}.stress_points[{index}].{name}",
                    owner=plan_name,
                )


class ProjectGenerationProcessor:
    def process(
        self,
        definition: ProjectGenerationDefinition,
        *,
        base_directory: str | pathlib.Path = ".",
    ) -> GeneratedProject:
        base_directory = pathlib.Path(base_directory)
        project_name, project_metadata = self._load_project_metadata(definition, base_directory)
        effective_definition = definition.model_copy(
            update={"project": definition.project.model_copy(update={"name": project_name, "metadata": project_metadata})}
        )
        pins = self._load_pins(effective_definition, base_directory)
        groups = self._generate_groups(effective_definition, pins)
        device_states = self._generate_device_states(effective_definition, groups)
        test_plan_request = GenerateTestPlansRequest(
            definition=effective_definition,
            groups=tuple(groups),
            device_states=tuple(device_states),
        )
        test_plans = self._generate_test_plans(test_plan_request)
        generated_project = GeneratedProject(
            name=project_name,
            metadata=project_metadata,
            dut_name=effective_definition.dut.name if effective_definition.dut else None,
            pins=tuple(pins),
            groups=tuple(groups),
            device_states=tuple(device_states),
            test_plans=tuple(test_plans),
        )
        ValidateGeneratedProjectRequest(
            definition=effective_definition,
            project=generated_project,
        ).validate()
        return generated_project


    def _load_project_metadata(
        self,
        definition: ProjectGenerationDefinition,
        base_directory: pathlib.Path,
    ) -> tuple[str, dict[str, Any]]:
        project_values: dict[str, Any] = {
            "name": definition.project.name,
            "metadata": dict(definition.project.metadata),
        }
        if definition.project.source is not None:
            try:
                source = definition.sources[definition.project.source]
            except KeyError as error:
                raise ProjectGenerationError(
                    f'Unknown project source "{definition.project.source}"',
                    code="project.unknown_source",
                    location="project.source",
                ) from error
            records = load_source_records(
                source,
                base_directory=base_directory,
                mappings=definition.mappings,
                formatters=definition.formatters,
            )
            if len(records) != 1:
                raise ProjectGenerationError(
                    f'Project source "{definition.project.source}" must resolve to exactly one record; received {len(records)}',
                    code="project.invalid_source_count",
                    location="project.source",
                )
            merge_value_tree(project_values, records[0])

        name = project_values.get("name")
        if name is None or not str(name).strip():
            raise ProjectGenerationError(
                "Project metadata does not define a name",
                code="project.missing_name",
                location="project.name",
            )
        metadata = project_values.get("metadata", {})
        if not isinstance(metadata, Mapping):
            raise ProjectGenerationError(
                "Project metadata must resolve to an object",
                code="project.invalid_metadata",
                location="project.metadata",
            )
        return str(name), dict(metadata)

    def _load_pins(self, definition: ProjectGenerationDefinition, base_directory: pathlib.Path) -> list[GeneratedPin]:
        if definition.dut is None:
            return []
        source = self._resolve_pin_source(definition, definition.dut)
        records = load_source_records(
            source,
            base_directory=base_directory,
            mappings=definition.mappings,
            formatters=definition.formatters,
        )
        namespace = uuid.uuid5(_PROJECT_GENERATION_NAMESPACE, f"{definition.project.name}:{definition.dut.name}")
        pins: list[GeneratedPin] = []
        designators: set[str] = set()
        for index, record in enumerate(records):
            designator = record.get("designator")
            name = record.get("name")
            if designator is None:
                raise ProjectGenerationError(
                    f"Pin record {index} does not define designator",
                    code="pin.missing_designator",
                    location=f"dut.pins.records[{index}]",
                    owner=definition.dut.name,
                )
            if name is None:
                raise ProjectGenerationError(
                    f"Pin record {index} does not define name",
                    code="pin.missing_name",
                    location=f"dut.pins.records[{index}]",
                    owner=definition.dut.name,
                )
            designator = str(designator)
            if designator in designators:
                raise ProjectGenerationError(
                    f'Duplicate pin designator "{designator}"',
                    code="pin.duplicate_designator",
                    location=f"dut.pins.records[{index}].designator",
                    owner=definition.dut.name,
                    context={"designator": designator},
                )
            designators.add(designator)
            parameters = record.get("parameters", {})
            if not isinstance(parameters, Mapping):
                raise ProjectGenerationError(f'Pin "{designator}" parameters must be an object')
            pins.append(
                GeneratedPin(
                    id=uuid.uuid5(namespace, designator),
                    designator=designator,
                    name=str(name),
                    parameters=dict(parameters),
                )
            )
        return pins

    @staticmethod
    def _resolve_pin_source(definition: ProjectGenerationDefinition, dut: DutDefinition) -> SourceDefinition:
        source = dut.pins.source
        if isinstance(source, str):
            try:
                return definition.sources[source]
            except KeyError as error:
                raise ProjectGenerationError(
                f'Unknown pin source "{source}"',
                code="source.unknown",
                location="dut.pins.source",
                owner=dut.name,
                context={"source": source},
            ) from error
        return source

    def _generate_groups(self, definition: ProjectGenerationDefinition, pins: list[GeneratedPin]) -> list[GeneratedGroup]:
        if definition.groups.external:
            return []
        by_designator = {pin.designator: pin for pin in pins}
        namespace = uuid.uuid5(_PROJECT_GENERATION_NAMESPACE, f"{definition.project.name}:groups")
        groups = [self._compile_explicit_group(group, by_designator, namespace) for group in definition.groups.explicit]
        for rule in definition.groups.generation:
            groups.extend(self._compile_group_rule(definition, rule, pins, namespace))
        names = [group.name for group in groups]
        duplicates = sorted({name for name in names if names.count(name) > 1})
        if duplicates:
            raise ProjectGenerationError(f"Duplicate generated group names: {', '.join(duplicates)}")
        return groups

    @staticmethod
    def _compile_explicit_group(
        definition: ExplicitGroupDefinition,
        by_designator: Mapping[str, GeneratedPin],
        namespace: uuid.UUID,
    ) -> GeneratedGroup:
        missing = [designator for designator in definition.pins if designator not in by_designator]
        if missing:
            raise ProjectGenerationError(
                f'Group "{definition.name}" references unknown pin designators: {", ".join(missing)}',
                code="group.unknown_pins",
                location=f'groups.explicit[{definition.name}].pins',
                owner=definition.name,
                context={"missing_designators": missing},
            )
        return GeneratedGroup(
            id=uuid.uuid5(namespace, definition.name),
            name=definition.name,
            group_type=definition.group_type,
            pin_ids=tuple(by_designator[designator].id for designator in definition.pins),
            parameters=dict(definition.parameters),
        )

    def _compile_group_rule(
        self,
        definition: ProjectGenerationDefinition,
        rule: GroupGenerationRule,
        pins: Iterable[GeneratedPin],
        namespace: uuid.UUID,
    ) -> list[GeneratedGroup]:
        selected = [pin for pin in pins if matches(rule.select.where, pin.context())]
        buckets: dict[tuple[Any, ...], list[GeneratedPin]] = {}
        for pin in selected:
            key = tuple(resolve_required_path(pin.context(), field, f'group rule "{rule.id}"') for field in rule.group_by)
            buckets.setdefault(key, []).append(pin)

        generated: list[GeneratedGroup] = []
        for key, bucket in buckets.items():
            partition = build_partition_context(rule.group_by, key)
            context = {
                "partition": partition,
                "members": [pin.context() for pin in bucket],
            }
            values = resolve_value_tree(rule.set, context, definition=definition)
            name = render_group_name(definition, rule, context)
            group_type = values.pop("group_type", None)
            if group_type is None:
                raise ProjectGenerationError(f'Group rule "{rule.id}" did not resolve group_type')
            parameters = values.pop("parameters", {})
            if values:
                parameters = {**parameters, **values}
            generated.append(
                GeneratedGroup(
                    id=uuid.uuid5(namespace, name),
                    name=name,
                    group_type=str(group_type),
                    pin_ids=tuple(pin.id for pin in bucket),
                    parameters=parameters,
                    generation_rule_id=rule.id,
                )
            )
        return generated

    def _generate_device_states(
        self,
        definition: ProjectGenerationDefinition,
        groups: list[GeneratedGroup],
    ) -> list[GeneratedDeviceState]:
        namespace = uuid.uuid5(_PROJECT_GENERATION_NAMESPACE, f"{definition.project.name}:device-states")
        by_name = {group.name: group for group in groups}
        resolved: dict[str, GeneratedDeviceState] = {}
        resolving: set[str] = set()

        def resolve_state(name: str) -> GeneratedDeviceState:
            if name in resolved:
                return resolved[name]
            if name in resolving:
                raise ProjectGenerationError(
                    f'Circular device-state inheritance involving "{name}"',
                    code="device_state.circular_inheritance",
                    location=f'device_states.{name}.extends',
                    owner=name,
                )
            try:
                state_definition = definition.device_states[name]
            except KeyError as error:
                raise ProjectGenerationError(
                    f'Unknown device state "{name}"',
                    code="device_state.unknown",
                    location=f'device_states.{name}',
                    owner=name,
                ) from error

            resolving.add(name)
            base = resolve_state(state_definition.extends) if state_definition.extends else None
            group_values = {group.group_name: dict(group.values) for group in base.group_states} if base else {}
            power_domains = list(base.power_domains) if base else []

            for group in groups:
                values = group_values.setdefault(group.name, {})
                context = {"group": group.as_group_record().context()}
                for rule in state_definition.rules:
                    if matches(rule.when, context):
                        merge_value_tree(values, resolve_value_tree(rule.set, context, definition=definition))

            for domain in state_definition.power_domains:
                missing = [group_name for group_name in domain.groups if group_name not in by_name]
                if missing and not definition.groups.external:
                    raise ProjectGenerationError(
                        f'Device state "{name}" power domain "{domain.name}" references unknown groups: {", ".join(missing)}'
                    )
                domain_groups = [by_name[group_name] for group_name in domain.groups if group_name in by_name]
                power_domains = [existing for existing in power_domains if existing.name != domain.name]
                power_domains.append(
                    GeneratedPowerDomain(
                        name=domain.name,
                        group_ids=tuple(group.id for group in domain_groups),
                        group_names=tuple(domain.groups),
                        assignment=domain.assignment,
                        bias=resolve_value_tree(domain.bias.model_dump(), {}, definition=definition),
                        timing=domain.timing.model_dump() if domain.timing else None,
                    )
                )

            allocation = state_definition.allocation.model_dump() if state_definition.allocation else (base.allocation if base else None)
            generated_group_states = tuple(
                GeneratedGroupState(group_id=by_name[group_name].id, group_name=group_name, values=values)
                for group_name, values in group_values.items()
                if group_name in by_name and values
            )
            generated = GeneratedDeviceState(
                id=uuid.uuid5(namespace, name),
                name=name,
                extends=state_definition.extends,
                allocation=allocation,
                power_domains=tuple(power_domains),
                group_states=generated_group_states,
                power_assignments=self._resolve_power_assignments(
                    definition=definition,
                    state_name=name,
                    allocation=allocation,
                    power_domains=power_domains,
                    group_states=generated_group_states,
                ),
                power_on_sequence=self._resolve_power_sequence(
                    state_name=name, power_domains=power_domains, event="power_on", default_order="declaration"
                ),
                power_off_sequence=self._resolve_power_sequence(
                    state_name=name, power_domains=power_domains, event="power_off", default_order="reverse_power_on"
                ),
            )
            resolving.remove(name)
            resolved[name] = generated
            return generated

        return [resolve_state(name) for name in definition.device_states]


    def _resolve_power_sequence(
        self,
        *,
        state_name: str,
        power_domains: list[GeneratedPowerDomain],
        event: str,
        default_order: str,
    ) -> tuple[GeneratedPowerSequenceStep, ...]:
        by_name = {domain.name: domain for domain in power_domains}
        if len(by_name) != len(power_domains):
            duplicates = sorted(
                {domain.name for domain in power_domains if sum(item.name == domain.name for item in power_domains) > 1}
            )
            raise ProjectGenerationError(
                f'Device state "{state_name}" has duplicate power-domain names: {", ".join(duplicates)}'
            )

        dependencies: dict[str, str | None] = {}
        has_explicit_timing = False
        for domain in power_domains:
            timing = (domain.timing.get(event) or {}) if domain.timing else {}
            has_explicit_timing = has_explicit_timing or bool(timing)
            after = timing.get("after")
            if after is not None:
                after = str(after)
                if after not in by_name:
                    raise ProjectGenerationError(
                        f'Device state "{state_name}" power domain "{domain.name}" references unknown timing domain "{after}"'
                    )
                if after == domain.name:
                    raise ProjectGenerationError(
                        f'Device state "{state_name}" power domain "{domain.name}" cannot {event.replace("_", " ")} after itself'
                    )
            dependencies[domain.name] = after

        if default_order == "reverse_power_on" and not has_explicit_timing:
            power_on = self._resolve_power_sequence(
                state_name=state_name, power_domains=power_domains, event="power_on", default_order="declaration"
            )
            ordered = [by_name[step.domain_name] for step in reversed(power_on)]
        else:
            ordered = []
            visiting: set[str] = set()
            visited: set[str] = set()

            def visit(name: str) -> None:
                if name in visited:
                    return
                if name in visiting:
                    raise ProjectGenerationError(
                        f'Device state "{state_name}" has a circular {event.replace("_", "-")} timing dependency involving "{name}"'
                    )
                visiting.add(name)
                dependency = dependencies[name]
                if dependency is not None:
                    visit(dependency)
                visiting.remove(name)
                visited.add(name)
                ordered.append(by_name[name])

            for domain in power_domains:
                visit(domain.name)

        steps: list[GeneratedPowerSequenceStep] = []
        for index, domain in enumerate(ordered):
            timing = (domain.timing.get(event) or {}) if domain.timing else {}
            steps.append(
                GeneratedPowerSequenceStep(
                    index=index,
                    domain_name=domain.name,
                    assignment=domain.assignment,
                    group_ids=domain.group_ids,
                    group_names=domain.group_names,
                    bias=dict(domain.bias),
                    delay=float(timing.get("delay", 0.0)),
                    after=dependencies[domain.name],
                )
            )
        return tuple(steps)


    @staticmethod
    def _resolve_power_assignments(
        *,
        definition: ProjectGenerationDefinition,
        state_name: str,
        allocation: Mapping[str, Any] | None,
        power_domains: list[GeneratedPowerDomain],
        group_states: tuple[GeneratedGroupState, ...],
    ) -> tuple[GeneratedPowerAssignment, ...]:
        assignments: dict[str, GeneratedPowerAssignment] = {}
        pseudo_resources = {"GROUND", "FLOATING"}

        def validate_assignment(assignment: str, owner: str) -> None:
            if assignment in pseudo_resources:
                return
            if assignment not in definition.power_resources:
                raise ProjectGenerationError(
                    f'Device state "{state_name}" {owner} references unknown power resource "{assignment}"'
                )

        for domain in power_domains:
            validate_assignment(domain.assignment, f'power domain "{domain.name}"')
            for group_id, group_name in zip(domain.group_ids, domain.group_names):
                assignments[group_name] = GeneratedPowerAssignment(
                    group_id=group_id,
                    group_name=group_name,
                    assignment=domain.assignment,
                    bias=dict(domain.bias),
                    source=f'power_domain:{domain.name}',
                )

        unassigned: list[GeneratedGroupState] = []
        for group_state in group_states:
            values = group_state.values
            bias = values.get("bias")
            if bias is None:
                continue
            if not isinstance(bias, Mapping):
                raise ProjectGenerationError(
                    f'Device state "{state_name}" group "{group_state.group_name}" bias must be an object'
                )
            assignment = values.get("assignment")
            if assignment is None:
                if group_state.group_name not in assignments:
                    unassigned.append(group_state)
                continue
            assignment = str(assignment)
            validate_assignment(assignment, f'group "{group_state.group_name}"')
            assignments[group_state.group_name] = GeneratedPowerAssignment(
                group_id=group_state.group_id,
                group_name=group_state.group_name,
                assignment=assignment,
                bias=dict(bias),
                source="group_rule",
            )

        mode = str(allocation.get("mode")) if allocation else "direct"
        if mode == "direct":
            if unassigned:
                names = ", ".join(group.group_name for group in unassigned)
                raise ProjectGenerationError(
                    f'Device state "{state_name}" uses direct allocation but has unassigned biased groups: {names}'
                )
            return tuple(assignments.values())

        if mode not in {"automatic", "hybrid"}:
            raise ProjectGenerationError(f'Device state "{state_name}" has unsupported allocation mode "{mode}"')

        strategy = allocation.get("strategy") if allocation else None
        if strategy not in {None, "first_available", "voltage_first"}:
            raise ProjectGenerationError(
                f'Device state "{state_name}" has unsupported allocation strategy "{strategy}"'
            )

        reserved = {str(resource) for resource in allocation.get("reserve", [])} if allocation else set()
        reserved.update(
            name for name, resource in definition.power_resources.items() if (resource.role or "").upper() == "STRESS"
        )
        used = {assignment.assignment for assignment in assignments.values() if assignment.assignment not in pseudo_resources}
        available = sorted(set(definition.power_resources) - reserved - used)

        ganging_policy_name = allocation.get("ganging_policy") if allocation else None
        try:
            ganging_policy = get_ganging_policy(str(ganging_policy_name) if ganging_policy_name is not None else None)
        except ValueError as error:
            raise ProjectGenerationError(f'Device state "{state_name}" {error}') from error

        if strategy == "voltage_first":
            unassigned.sort(
                key=lambda group: (
                    -abs(float(group.values.get("bias", {}).get("level", 0.0) or 0.0)),
                    group.group_name,
                )
            )
        else:
            unassigned.sort(key=lambda group: group.group_name)

        for group_state in unassigned:
            bias = dict(group_state.values["bias"])
            eligible_existing = (
                ExistingPowerAssignment(
                    group_name=assignment.group_name,
                    assignment=assignment.assignment,
                    bias=assignment.bias,
                )
                for assignment in assignments.values()
                if assignment.assignment not in pseudo_resources and assignment.assignment not in reserved
            )
            resource_name = ganging_policy.propose_assignment(
                GangingCandidate(group_name=group_state.group_name, bias=bias),
                eligible_existing,
            )
            source = f"ganged:{ganging_policy.name}" if resource_name is not None else "automatic"

            if resource_name is None:
                if not available:
                    remaining = ", ".join(
                        group.group_name for group in unassigned if group.group_name not in assignments
                    )
                    raise ProjectGenerationError(
                        f'Device state "{state_name}" does not have enough available power resources for: {remaining}'
                    )
                resource_name = available.pop(0)

            assignments[group_state.group_name] = GeneratedPowerAssignment(
                group_id=group_state.group_id,
                group_name=group_state.group_name,
                assignment=resource_name,
                bias=bias,
                source=source,
            )

        return tuple(assignments.values())

    def _generate_test_plans(self, request: GenerateTestPlansRequest) -> list[GeneratedTestPlan]:
        request.validate()

        definition = request.definition
        groups = list(request.groups)
        device_states = list(request.device_states)
        by_name = {group.name: group for group in groups}
        namespace = uuid.uuid5(_PROJECT_GENERATION_NAMESPACE, f"{definition.project.name}:test-plans")
        states_by_name = {state.name: state for state in device_states}
        plans = [self._compile_explicit_test_plan(plan, by_name, states_by_name, namespace) for plan in definition.test_plans]

        for rule in definition.test_plan_generation.rules:
            selected_groups = self._select_groups(groups, rule)
            plans.extend(
                self._generate_test_plans_for_rule(
                    rule=rule,
                    groups=selected_groups,
                    device_states=states_by_name,
                    namespace=namespace,
                )
            )

        names = [plan.name for plan in plans]
        duplicates = sorted({name for name in names if names.count(name) > 1})
        if duplicates:
            raise ProjectGenerationError(f"Duplicate generated test plan names: {', '.join(duplicates)}")
        return plans

    @staticmethod
    def _select_groups(
        groups: Iterable[GeneratedGroup],
        rule: TestPlanRuleDefinition,
    ) -> list[GeneratedGroup]:
        selected: list[GeneratedGroup] = []
        for group in groups:
            group_context = group.as_group_record().context()
            if matches(rule.groups.select.where, {"group": group_context, **group_context}):
                selected.append(group)
        return selected

    def _generate_test_plans_for_rule(
        self,
        *,
        rule: TestPlanRuleDefinition,
        groups: list[GeneratedGroup],
        device_states: Mapping[str, GeneratedDeviceState],
        namespace: uuid.UUID,
    ) -> list[GeneratedTestPlan]:
        group_records = [group.as_group_record() for group in groups]
        group_by_name = {record.name: generated for record, generated in zip(group_records, groups, strict=True)}
        plans: list[GeneratedTestPlan] = []

        for candidate in expand_rule(rule, group_records):
            if candidate.excluded:
                continue

            test_groups: list[GeneratedTestGroup] = []
            for group_record in candidate.partition.groups:
                values, excluded = resolve_group_values_and_exclusion(candidate, group_record, rule.overrides)
                if excluded:
                    continue

                stress_definitions = values.get("stress_parameters", {})
                if not isinstance(stress_definitions, Mapping):
                    raise ProjectGenerationError(f'Test plan rule "{rule.id}" stress_parameters must be an object')

                context = candidate_context(candidate, values=values, group=group_record)
                try:
                    stress_points = tuple(expand_stress_parameters(stress_definitions, context))
                except ValueError as error:
                    raise ProjectGenerationError(
                        f'Test plan rule "{rule.id}" failed to expand stress parameters for group "{group_record.name}": {error}'
                    ) from error

                generated_group = group_by_name[group_record.name]
                test_groups.append(
                    GeneratedTestGroup(
                        group_id=generated_group.id,
                        group_name=generated_group.name,
                        stress_points=stress_points,
                    )
                )

            if not test_groups:
                continue

            values = dict(candidate.values)
            context = candidate_context(candidate)
            name = render_value_template(values.get("name"), context, owner=f'test plan rule "{rule.id}" name')
            test_type = values.get("test_type")
            if not test_type:
                raise ProjectGenerationError(f'Test plan rule "{rule.id}" did not resolve test_type')

            plans.append(
                GeneratedTestPlan(
                    id=uuid.uuid5(namespace, name),
                    name=name,
                    test_type=str(test_type),
                    dimensions=dict(candidate.dimensions),
                    device_state=str(values["device_state"]) if values.get("device_state") is not None else None,
                    device_state_id=self._resolve_device_state_id(values.get("device_state"), device_states, rule.id),
                    test_groups=tuple(test_groups),
                    generation_rule_id=rule.id,
                )
            )

        return plans

    @staticmethod
    def _resolve_device_state_id(
        state_name: Any,
        states_by_name: Mapping[str, GeneratedDeviceState],
        owner: str,
    ) -> uuid.UUID | None:
        if state_name is None:
            return None
        state_name = str(state_name)
        try:
            return states_by_name[state_name].id
        except KeyError as error:
            raise ProjectGenerationError(
                f'"{owner}" references unknown device state "{state_name}"',
                code="test_plan.unknown_device_state",
                location=f'test_plans.{owner}.device_state',
                owner=owner,
                context={"device_state": state_name},
            ) from error

    @staticmethod
    def _compile_explicit_test_plan(
        definition: ExplicitTestPlanDefinition,
        by_name: Mapping[str, GeneratedGroup],
        states_by_name: Mapping[str, GeneratedDeviceState],
        namespace: uuid.UUID,
    ) -> GeneratedTestPlan:
        test_groups: list[GeneratedTestGroup] = []
        for test_group in definition.test_groups:
            try:
                group = by_name[test_group.group]
            except KeyError as error:
                raise ProjectGenerationError(
                    f'Test plan "{definition.name}" references unknown group "{test_group.group}"'
                ) from error
            test_groups.append(
                GeneratedTestGroup(
                    group_id=group.id,
                    group_name=group.name,
                    stress_points=tuple(StressPoint(values=dict(point)) for point in test_group.stress_points),
                )
            )
        return GeneratedTestPlan(
            id=uuid.uuid5(namespace, definition.name),
            name=definition.name,
            test_type=definition.test_type,
            dimensions=dict(definition.dimensions),
            device_state=definition.device_state,
            device_state_id=ProjectGenerationProcessor._resolve_device_state_id(
                definition.device_state, states_by_name, definition.name
            ),
            test_groups=tuple(test_groups),
        )


def load_source_records(
    source: SourceDefinition,
    *,
    base_directory: pathlib.Path,
    mappings: Mapping[str, Mapping[str, Any]] | None = None,
    formatters: Mapping[str, FormatterDefinition] | None = None,
) -> list[dict[str, Any]]:
    if isinstance(source, InlineSource):
        records = source.records
    elif isinstance(source, JsonSource):
        data = json.loads((base_directory / source.path).read_text(encoding="utf-8"))
        records = select_json_records(data, source.select)
    elif isinstance(source, CsvSource):
        with (base_directory / source.path).open("r", encoding="utf-8-sig", newline="") as file:
            records = list(csv.DictReader(file))
    elif isinstance(source, ExcelSource):
        try:
            import openpyxl
        except ImportError as error:
            raise ProjectGenerationError("Excel sources require the optional 'excel' dependency") from error
        workbook = openpyxl.load_workbook(base_directory / source.path, read_only=True, data_only=True)
        worksheet = workbook[source.sheet] if isinstance(source.sheet, str) else workbook.worksheets[source.sheet or 0]
        rows = worksheet.iter_rows(values_only=True)
        try:
            headers = [str(value) for value in next(rows)]
        except StopIteration:
            records = []
        else:
            records = [dict(zip(headers, row, strict=False)) for row in rows]
    else:
        raise TypeError(f"Unsupported source type: {type(source).__name__}")

    mapping = getattr(source, "mapping", {})
    return [
        apply_record_mapping(record, mapping, mappings=mappings, formatters=formatters) if mapping else dict(record)
        for record in records
    ]


def select_json_records(data: Any, selector: str | None) -> list[dict[str, Any]]:
    if selector is None or selector == "$":
        selected = data
    else:
        if not selector.startswith("$."):
            raise ProjectGenerationError(f'Unsupported JSON selector "{selector}"')
        selected = data
        for part in selector[2:].split("."):
            is_array = part.endswith("[*]")
            name = part[:-3] if is_array else part
            if not isinstance(selected, Mapping) or name not in selected:
                raise ProjectGenerationError(f'JSON selector "{selector}" did not match')
            selected = selected[name]
            if is_array and not isinstance(selected, list):
                raise ProjectGenerationError(f'JSON selector "{selector}" expected an array at "{name}"')
    if isinstance(selected, Mapping):
        return [dict(selected)]
    if not isinstance(selected, list) or any(not isinstance(record, Mapping) for record in selected):
        raise ProjectGenerationError(f'JSON selector "{selector or "$"}" must resolve to an object or array of objects')
    return [dict(record) for record in selected]


def apply_record_mapping(
    record: Mapping[str, Any],
    mapping: Mapping[str, str | SourceFieldMapping],
    *,
    mappings: Mapping[str, Mapping[str, Any]] | None = None,
    formatters: Mapping[str, FormatterDefinition] | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for target, field_mapping in mapping.items():
        if isinstance(field_mapping, str):
            source_path = field_mapping
            value_mapping_name = None
            formatter_name = None
        else:
            source_path = field_mapping.from_
            value_mapping_name = field_mapping.mapping
            formatter_name = field_mapping.formatter

        value = resolve_required_path(record, source_path, "source mapping")
        if value_mapping_name:
            try:
                value = (mappings or {})[value_mapping_name][str(value)]
            except KeyError as error:
                raise ProjectGenerationError(
                    f'Value "{value}" is not present in mapping "{value_mapping_name}"'
                ) from error
        if formatter_name:
            try:
                formatter = (formatters or {})[formatter_name]
            except KeyError as error:
                raise ProjectGenerationError(f'Unknown formatter "{formatter_name}"') from error
            value = apply_formatter(value, formatter)
        set_path(result, target, value)
    return result


def build_partition_context(fields: list[str], key: tuple[Any, ...]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for field, value in zip(fields, key, strict=True):
        set_path(result, field, value)
    return result


def resolve_value_tree(
    value: Any,
    context: Mapping[str, Any],
    *,
    definition: ProjectGenerationDefinition | None = None,
) -> Any:
    if isinstance(value, Mapping):
        reference_keys = {"from", "aggregate", "mapping", "formatter"}
        if "from" in value and set(value).issubset(reference_keys):
            resolved = resolve_value_reference(value, context)
            mapping_name = value.get("mapping")
            if mapping_name:
                if definition is None:
                    raise ProjectGenerationError("Mapped value references require a project definition")
                try:
                    resolved = definition.mappings[str(mapping_name)][str(resolved)]
                except KeyError as error:
                    raise ProjectGenerationError(
                        f'Value "{resolved}" is not present in mapping "{mapping_name}"'
                    ) from error
            formatter_name = value.get("formatter")
            if formatter_name:
                if definition is None:
                    raise ProjectGenerationError("Formatted value references require a project definition")
                try:
                    formatter = definition.formatters[str(formatter_name)]
                except KeyError as error:
                    raise ProjectGenerationError(f'Unknown formatter "{formatter_name}"') from error
                resolved = apply_formatter(resolved, formatter)
            return resolved

        result: dict[str, Any] = {}
        for key, child in value.items():
            resolved = resolve_value_tree(child, context, definition=definition)
            set_path(result, key, resolved)
        return result
    if isinstance(value, list):
        return [resolve_value_tree(child, context, definition=definition) for child in value]
    return value


def resolve_value_reference(reference: Mapping[str, Any], context: Mapping[str, Any]) -> Any:
    path = str(reference["from"])
    aggregate = reference.get("aggregate")
    if aggregate is None:
        return resolve_required_path(context, path, "value reference")

    collection_name, separator, member_path = path.partition(".")
    collection = context.get(collection_name)
    if not separator or not isinstance(collection, list):
        raise ProjectGenerationError(
            f'Aggregate value reference "{path}" must start with a list-valued context field'
        )
    values = [resolve_required_path(item, member_path, "aggregate value reference") for item in collection]
    if not values:
        raise ProjectGenerationError(f'Aggregate value reference "{path}" has no values')

    aggregate_name = str(aggregate)
    if aggregate_name == "min":
        return min(values)
    if aggregate_name == "max":
        return max(values)
    if aggregate_name == "first":
        return values[0]
    raise ProjectGenerationError(f'Unsupported aggregate "{aggregate_name}"')


def merge_value_tree(target: dict[str, Any], source: Mapping[str, Any]) -> dict[str, Any]:
    for key, value in source.items():
        if isinstance(value, Mapping) and isinstance(target.get(key), dict):
            merge_value_tree(target[key], value)
        else:
            target[key] = value
    return target


def render_group_name(
    definition: ProjectGenerationDefinition,
    rule: GroupGenerationRule,
    context: Mapping[str, Any],
) -> str:
    values: dict[str, str] = {}
    for field_name, field in rule.name.fields.items():
        value = resolve_required_path(context, field.source, f'group name field "{field_name}"')
        if field.mapping:
            try:
                value = definition.mappings[field.mapping][str(value)]
            except KeyError as error:
                raise ProjectGenerationError(f'Value "{value}" is not present in mapping "{field.mapping}"') from error
        if field.formatter:
            value = apply_formatter(value, definition.formatters[field.formatter])
        values[field_name] = str(value)
    try:
        return rule.name.template.format_map(values)
    except KeyError as error:
        raise ProjectGenerationError(f'Group name template references undefined field "{error.args[0]}"') from error


def render_value_template(definition: Any, context: Mapping[str, Any], *, owner: str) -> str:
    if isinstance(definition, str):
        template = definition
    elif isinstance(definition, Mapping) and isinstance(definition.get("template"), str):
        template = definition["template"]
    else:
        raise ProjectGenerationError(f"{owner} must be a string or template object")

    def replace(match: re.Match[str]) -> str:
        path = match.group(1)
        return str(resolve_required_path(context, path, owner))

    return _TEMPLATE_FIELD.sub(replace, template)


def apply_formatter(value: Any, formatter: FormatterDefinition) -> str:
    if formatter.type != "decimal_token":
        raise ProjectGenerationError(f'Unsupported formatter type "{formatter.type}"')
    decimal_places = formatter.decimal_places if formatter.decimal_places is not None else 1
    separator = formatter.separator if formatter.separator is not None else "V"
    formatted = f"{float(value):.{decimal_places}f}"
    whole, _, fraction = formatted.partition(".")
    return whole if decimal_places == 0 else f"{whole}{separator}{fraction}"


def resolve_required_path(context: Mapping[str, Any], path: str, owner: str) -> Any:
    value = resolve_path(context, path)
    if value is None:
        raise ProjectGenerationError(f'{owner} could not resolve path "{path}"')
    return value


def set_path(target: dict[str, Any], path: str, value: Any) -> None:
    current = target
    parts = path.split(".")
    for part in parts[:-1]:
        child = current.setdefault(part, {})
        if not isinstance(child, dict):
            raise ProjectGenerationError(f'Cannot assign nested path "{path}"')
        current = child
    current[parts[-1]] = value
