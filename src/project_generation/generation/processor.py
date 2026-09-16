import pathlib
import uuid
from dataclasses import replace
from typing import Any, Iterable, Mapping

from project_generation.definition.models import (
    DutDefinition,
    ExplicitTestPlanDefinition,
    NameTemplateDefinition,
    ProjectGenerationDefinition,
    SourceDefinition,
    TestPlanRuleDefinition,
)
from project_generation.diagnostics import (
    ProjectGenerationError,
    StressSupplyCandidateDiagnostic,
    StressSupplyResolutionError,
    StressSupplyResolutionIssue,
)
from project_generation.generation.hardware import BiasedPulseStress, SourceSwitchStressStrategy
from project_generation.generation.device_states import DeviceStateGenerator
from project_generation.generation.groups import GroupGenerator
from project_generation.generation.sources import load_source_records
from project_generation.generation.snapshot import GenerationSnapshot
from project_generation.generation.models import (
    GeneratedDeviceState,
    GeneratedGroup,
    GeneratedPin,
    GeneratedProject,
    GeneratedTestGroup,
    GeneratedTestPlan,
    GeneratedStressSupplyAssignment,
    GeneratedTemperatureControl,
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
from project_generation.generation.values import (
    _OMIT,
    merge_value_tree,
    render_value_template,
    resolve_value_tree,
)
from project_generation.generation.hardware import (
    load_hardware_power_resources,
    merge_hardware_power_resources,
    hardware_power_resource,
)
from project_generation.version import get_package_version

_PACKAGE_VERSION = get_package_version()
_PROJECT_GENERATION_NAMESPACE = uuid.UUID("b5cc252e-8608-4e8c-a03f-8ce6e5f55b43")

class ProjectGenerationProcessor:
    def process(
        self,
        definition: ProjectGenerationDefinition,
        *,
        base_directory: str | pathlib.Path | None = None,
    ) -> GeneratedProject:
        return self.process_with_snapshot(definition, base_directory=base_directory).generated_project

    def process_with_snapshot(
        self,
        definition: ProjectGenerationDefinition,
        *,
        base_directory: str | pathlib.Path | None = None,
    ) -> GenerationSnapshot:
        if definition.definition_directory is not None:
            base_directory = definition.definition_directory
        elif base_directory is None:
            base_directory = pathlib.Path.cwd()
        else:
            base_directory = pathlib.Path(base_directory)
        power_resources = self._load_power_resources(definition, base_directory)
        definition = definition.model_copy(update={"power_resources": power_resources})
        project_name, project_metadata = self._load_project_metadata(definition, base_directory)
        effective_project = definition.project.model_copy(update={"name": project_name, "metadata": project_metadata})
        effective_definition = definition.model_copy(update={"project": effective_project})
        dut_name = self._resolve_dut_name(effective_definition)
        if effective_definition.dut is not None:
            effective_definition = effective_definition.model_copy(
                update={"dut": effective_definition.dut.model_copy(update={"name": dut_name})}
            )
        pins = self._load_pins(effective_definition, base_directory)
        groups = GroupGenerator(effective_definition, pins).generate()
        device_states = DeviceStateGenerator(effective_definition, groups).generate()
        test_plan_request = GenerateTestPlansRequest(
            definition=effective_definition,
            groups=tuple(groups),
            device_states=tuple(device_states),
        )
        test_plans = self._generate_test_plans(test_plan_request)
        test_plans = self._resolve_stress_supplies(effective_definition, test_plans)
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
        return GenerationSnapshot(
            definition=effective_definition,
            pins=tuple(pins),
            groups=tuple(groups),
            device_states=tuple(device_states),
            test_plans=tuple(test_plans),
            generated_project=generated_project,
        )

    def _resolve_dut_name(self, definition: ProjectGenerationDefinition) -> str | None:
        if definition.dut is None:
            return None

        name_definition = definition.dut.name
        context = {
            "project": {
                "name": definition.project.name,
                "metadata": dict(definition.project.metadata),
            }
        }
        if isinstance(name_definition, str):
            name = name_definition
        elif isinstance(name_definition, NameTemplateDefinition):
            name = render_value_template(
                name_definition.model_dump(by_alias=True, exclude_none=True),
                context,
                owner="DUT name",
                mappings=definition.mappings,
                formatters=definition.formatters,
            )
        else:
            name = resolve_value_tree(name_definition, context, definition=definition)

        if name is _OMIT or name is None or not str(name).strip():
            raise ProjectGenerationError(
                "DUT name did not resolve to a non-empty value",
                code="dut.missing_name",
                location="dut.name",
            )
        return str(name)

    @staticmethod
    def _load_power_resources(
        definition: ProjectGenerationDefinition,
        base_directory: pathlib.Path,
    ) -> dict[str, Any]:
        if definition.hardware is None:
            return dict(definition.power_resources)

        source_path = pathlib.Path(definition.hardware.source)
        if not source_path.is_absolute():
            source_path = base_directory / source_path
        hardware_resources = load_hardware_power_resources(source_path)
        return merge_hardware_power_resources(hardware_resources, definition.power_resources)

    def _load_project_metadata(
        self,
        definition: ProjectGenerationDefinition,
        base_directory: pathlib.Path,
    ) -> tuple[str, dict[str, Any]]:
        project_values: dict[str, Any] = {
            "name": definition.project.name,
            "metadata": dict(definition.project.metadata),
        }
        project_values["metadata"]["project_generator_version"] = _PACKAGE_VERSION
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

            temperature_control = self._resolve_temperature_control(definition, values, candidate)

            plans.append(
                GeneratedTestPlan(
                    id=uuid.uuid5(namespace, name),
                    name=name,
                    test_type=str(test_type),
                    dimensions=dict(candidate.dimensions),
                    device_state=str(values["device_state"]) if values.get("device_state") is not None else None,
                    device_state_id=self._resolve_device_state_id(values.get("device_state"), device_states, rule.id),
                    test_groups=tuple(test_groups),
                    temperature_control=temperature_control,
                    generation_rule_id=rule.id,
                )
            )

        return plans

    @staticmethod
    def _resolve_temperature_control(
        definition: ProjectGenerationDefinition,
        values: Mapping[str, Any],
        candidate: Any,
    ) -> GeneratedTemperatureControl | None:
        config = values.get("temperature_control")
        if config is None:
            return None
        if not isinstance(config, Mapping):
            raise ProjectGenerationError("temperature_control must be an object")

        context = candidate_context(candidate)
        context["project"] = {
            "name": definition.project.name,
            "metadata": dict(definition.project.metadata),
        }
        resolved = resolve_value_tree(config, context, definition=definition)
        if not isinstance(resolved, Mapping):
            raise ProjectGenerationError("temperature_control must resolve to an object")

        try:
            return GeneratedTemperatureControl(
                enabled=bool(resolved.get("enabled", True)),
                temperature=float(resolved.get("temperature", 25.0)),
                soak_time=float(resolved.get("soak_time", 0.0)),
                factor=float(resolved.get("factor", 1.0)),
                offset=float(resolved.get("offset", 0.0)),
                start_tolerance=float(resolved.get("start_tolerance", 10.0)),
                cool_temperature=float(resolved.get("cool_temperature", 24.0)),
                timeout=float(resolved.get("timeout", 900.0)),
            )
        except (TypeError, ValueError) as error:
            raise ProjectGenerationError(f"Invalid temperature_control value: {error}") from error

    @staticmethod
    def _resolve_stress_supplies(
        definition: ProjectGenerationDefinition,
        test_plans: list[GeneratedTestPlan],
    ) -> list[GeneratedTestPlan]:
        hardware_stress_resources = {
            name: hardware_power_resource(name, resource)
            for name, resource in definition.power_resources.items()
            if resource.parameters.get("hardware") and (resource.role or "BIAS").upper() == "STRESS"
        }
        if not hardware_stress_resources:
            return test_plans

        strategy = SourceSwitchStressStrategy()
        resolved: list[GeneratedTestPlan] = []
        issues: list[StressSupplyResolutionIssue] = []

        for plan in test_plans:
            compatible_names = set(hardware_stress_resources)
            point_diagnostics: list[StressSupplyResolutionIssue] = []

            for test_group in plan.test_groups:
                for point_index, stress_point in enumerate(test_group.stress_points):
                    try:
                        stress = BiasedPulseStress.from_stress_point(stress_point.values)
                    except (KeyError, TypeError, ValueError):
                        # Not every test family is necessarily a biased-pulse stress. Only apply this
                        # strategy to stress definitions that provide a peak.
                        if "peak" not in stress_point.values:
                            continue
                        raise ProjectGenerationError(
                            f'Test plan "{plan.name}" has an invalid biased-pulse stress point',
                            code="stress.invalid_biased_pulse",
                            location=f"test_plans.{plan.name}.{test_group.group_name}.stress_points[{point_index}]",
                        )

                    candidates: list[StressSupplyCandidateDiagnostic] = []
                    accepted_for_point: set[str] = set()
                    for name, resource in sorted(hardware_stress_resources.items()):
                        compatibility = strategy.evaluate(resource, stress)
                        if compatibility.accepted:
                            accepted_for_point.add(name)
                        candidates.append(
                            StressSupplyCandidateDiagnostic(
                                resource=name,
                                strategy=strategy.name,
                                accepted=compatibility.accepted,
                                reason=compatibility.reason,
                            )
                        )
                    compatible_names &= accepted_for_point
                    if not accepted_for_point:
                        point_diagnostics.append(
                            StressSupplyResolutionIssue(
                                plan_name=plan.name,
                                group_name=test_group.group_name,
                                stress_point_index=point_index,
                                stress=stress_point.values,
                                candidates=tuple(candidates),
                            )
                        )

            if point_diagnostics:
                issues.extend(point_diagnostics)
                resolved.append(plan)
                continue

            if plan.test_groups and any(group.stress_points for group in plan.test_groups):
                if not compatible_names:
                    # Individual points may each be supportable by different supplies, but a plan must
                    # resolve one stress source that can execute the whole stress series.
                    first_group = next(group for group in plan.test_groups if group.stress_points)
                    candidates = tuple(
                        StressSupplyCandidateDiagnostic(
                            resource=name,
                            strategy=strategy.name,
                            accepted=False,
                            reason="cannot satisfy every stress point in this test plan",
                        )
                        for name in sorted(hardware_stress_resources)
                    )
                    issues.append(
                        StressSupplyResolutionIssue(
                            plan_name=plan.name,
                            group_name=first_group.group_name,
                            stress_point_index=0,
                            stress=first_group.stress_points[0].values,
                            candidates=candidates,
                        )
                    )
                    resolved.append(plan)
                    continue

                resource_name = sorted(compatible_names)[0]
                resolved.append(
                    replace(
                        plan,
                        stress_supply=GeneratedStressSupplyAssignment(
                            resource=resource_name,
                            strategy=strategy.name,
                        ),
                    )
                )
            else:
                resolved.append(plan)

        if issues:
            raise StressSupplyResolutionError(tuple(issues))
        return resolved


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
