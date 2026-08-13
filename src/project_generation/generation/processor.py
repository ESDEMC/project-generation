import csv
import json
import pathlib
import re
import uuid
from typing import Any, Iterable, Mapping

from project_generation.definition.models import (
    CsvSource,
    DutDefinition,
    ExcelSource,
    ExplicitGroupDefinition,
    ExplicitTestPlanDefinition,
    FormatterDefinition,
    GroupGenerationRule,
    InlineSource,
    JsonSource,
    JsonValue,
    ProjectGenerationDefinition,
    SourceDefinition,
    SourceFieldMapping,
    TestPlanRuleDefinition,
)
from project_generation.diagnostics import ProjectGenerationError
from project_generation.generation.ganging import ExistingPowerAssignment, GangingCandidate, get_ganging_policy
from project_generation.generation.models import (
    GeneratedDeviceState,
    GeneratedGroup,
    GeneratedGroupState,
    GeneratedPin,
    GeneratedPowerAssignment,
    GeneratedPowerDomain,
    GeneratedPowerSequenceStep,
    GeneratedProject,
    GeneratedTestGroup,
    GeneratedTestPlan,
)
from project_generation.generation.rules import (
    GroupRecord,
    StressPoint,
    candidate_context,
    expand_rule,
    expand_stress_parameters,
    matches,
    resolve_group_values_and_exclusion,
    resolve_path,
)
from project_generation.generation.validation import GenerateTestPlansRequest, ValidateGeneratedProjectRequest

_PROJECT_GENERATION_NAMESPACE = uuid.UUID("b5cc252e-8608-4e8c-a03f-8ce6e5f55b43")
_TEMPLATE_FIELD = re.compile(r"\{([^{}]+)}")
_OMIT = object()

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
                    definition=definition,
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
        definition: ProjectGenerationDefinition,
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
            name = render_value_template(
                values.get("name"),
                context,
                owner=f'test plan rule "{rule.id}" name',
                mappings=definition.mappings,
                formatters=definition.formatters,
            )
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
        if is_value_definition(value):
            return resolve_value_definition(value, context, definition=definition)

        result: dict[str, Any] = {}
        for key, child in value.items():
            resolved = resolve_value_tree(child, context, definition=definition)
            if resolved is _OMIT:
                continue
            set_path(result, key, resolved)
        return result

    if isinstance(value, list):
        if is_conditional_value_definition_list(value):
            for definition_entry in value:
                resolved = resolve_value_definition(definition_entry, context, definition=definition)
                if resolved is not _OMIT:
                    return resolved
            return _OMIT

        resolved_items = [resolve_value_tree(child, context, definition=definition) for child in value]
        return [item for item in resolved_items if item is not _OMIT]

    return value


def is_value_definition(value: Mapping[str, Any]) -> bool:
    definition_keys = {"from", "value", "aggregate", "mapping", "formatter", "cast", "when"}
    if not set(value).issubset(definition_keys):
        return False
    return "from" in value or "value" in value


def is_conditional_value_definition_list(value: list[Any]) -> bool:
    if not value or not all(isinstance(item, Mapping) and is_value_definition(item) for item in value):
        return False
    return any("when" in item for item in value)


def resolve_value_definition(
    value: Mapping[str, Any],
    context: Mapping[str, Any],
    *,
    definition: ProjectGenerationDefinition | None = None,
) -> Any:
    when = value.get("when")
    if when is not None:
        if not isinstance(when, Mapping):
            raise ProjectGenerationError('Value definition "when" must be an object')
        if not matches(when, context):
            return _OMIT

    if "from" in value:
        resolved = resolve_value_reference(value, context)
    else:
        resolved = value.get("value")

    mapping_name = value.get("mapping")
    if mapping_name:
        if definition is None:
            raise ProjectGenerationError("Mapped value references require a project definition")
        try:
            resolved = definition.mappings[str(mapping_name)][str(resolved)]
        except KeyError as error:
            raise ProjectGenerationError(f'Value "{resolved}" is not present in mapping "{mapping_name}"') from error

    cast_name = value.get("cast")
    if cast_name:
        resolved = cast_value(resolved, str(cast_name))

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


def cast_value(value: Any, cast_name: str) -> Any:
    try:
        if cast_name == "float":
            return float(value)
        if cast_name == "int":
            return int(value)
        if cast_name == "str":
            return str(value)
        if cast_name == "bool":
            if isinstance(value, str):
                normalized = value.strip().lower()
                if normalized in {"true", "1", "yes", "on"}:
                    return True
                if normalized in {"false", "0", "no", "off"}:
                    return False
                raise ValueError(value)
            return bool(value)
    except (TypeError, ValueError) as error:
        raise ProjectGenerationError(f'Cannot cast value "{value}" to {cast_name}') from error

    raise ProjectGenerationError(f'Unsupported cast "{cast_name}"')


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
        value = min(values)
    elif aggregate_name == "max":
        value = max(values)
    elif aggregate_name == "first":
        value = values[0]
    else:
        raise ProjectGenerationError(f'Unsupported aggregate "{aggregate_name}"')

    return value


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


def render_value_template(
    definition: Any,
    context: Mapping[str, Any],
    *,
    owner: str,
    mappings: Mapping[str, Mapping[str, JsonValue]] | None = None,
    formatters: Mapping[str, FormatterDefinition] | None = None,
) -> str:
    if isinstance(definition, str):
        template = definition
        fields: Mapping[str, Any] = {}
    elif isinstance(definition, Mapping) and isinstance(definition.get("template"), str):
        template = definition["template"]
        fields = definition.get("fields", {})
        if not isinstance(fields, Mapping):
            raise ProjectGenerationError(f"{owner} fields must be an object")
    else:
        raise ProjectGenerationError(f"{owner} must be a string or template object")

    field_values: dict[str, Any] = {}
    for field_name, field_definition in fields.items():
        if not isinstance(field_definition, Mapping):
            raise ProjectGenerationError(f'{owner} field "{field_name}" must be an object')
        source = field_definition.get("source")
        if not isinstance(source, str):
            raise ProjectGenerationError(f'{owner} field "{field_name}" must define source')
        value = resolve_required_path(context, source, f'{owner} field "{field_name}"')

        mapping_name = field_definition.get("mapping")
        if mapping_name is not None:
            try:
                value = (mappings or {})[str(mapping_name)][str(value)]
            except KeyError as error:
                raise ProjectGenerationError(
                    f'Value "{value}" is not present in mapping "{mapping_name}" for {owner} field "{field_name}"'
                ) from error

        formatter_name = field_definition.get("formatter")
        if formatter_name is not None:
            try:
                formatter = (formatters or {})[str(formatter_name)]
            except KeyError as error:
                raise ProjectGenerationError(f'Unknown formatter "{formatter_name}" for {owner} field "{field_name}"') from error
            value = apply_formatter(value, formatter)

        field_values[str(field_name)] = value

    def replace(match: re.Match[str]) -> str:
        path = match.group(1)
        if path in field_values:
            return str(field_values[path])
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
