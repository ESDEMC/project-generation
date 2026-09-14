import uuid
from dataclasses import replace
from typing import Any, Iterable, Mapping

from project_generation.definition.models import ExplicitTestPlanDefinition, ProjectGenerationDefinition, TestPlanRuleDefinition
from project_generation.diagnostics import (
    ProjectGenerationError,
    StressSupplyCandidateDiagnostic,
    StressSupplyResolutionError,
    StressSupplyResolutionIssue,
)
from project_generation.generation.hardware import hardware_power_resource
from project_generation.generation.hardware_domain import BiasedPulseStress, SourceSwitchStressStrategy
from project_generation.generation.helpers import render_value_template, resolve_value_tree
from project_generation.generation.models import (
    GeneratedDeviceState,
    GeneratedGroup,
    GeneratedStressSupplyAssignment,
    GeneratedTemperatureControl,
    GeneratedTestGroup,
    GeneratedTestPlan,
)
from project_generation.generation.rules import (
    StressPoint,
    candidate_context,
    expand_rule,
    expand_stress_parameters,
    matches,
    resolve_group_values_and_exclusion,
)
from project_generation.generation.validation import GenerateTestPlansRequest

_PROJECT_GENERATION_NAMESPACE = uuid.UUID("b5cc252e-8608-4e8c-a03f-8ce6e5f55b43")


class TestPlanGenerator:
    def generate(self, request: GenerateTestPlansRequest) -> list[GeneratedTestPlan]:
        return self._generate_test_plans(request)

    def resolve_stress_supplies(
        self,
        definition: ProjectGenerationDefinition,
        test_plans: list[GeneratedTestPlan],
    ) -> list[GeneratedTestPlan]:
        return self._resolve_stress_supplies(definition, test_plans)

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
            device_state_id=TestPlanGenerator._resolve_device_state_id(
                definition.device_state, states_by_name, definition.name
            ),
            test_groups=tuple(test_groups),
        )
