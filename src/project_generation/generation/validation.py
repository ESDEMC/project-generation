import math
import uuid
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from project_generation.definition.models import ProjectGenerationDefinition
from project_generation.diagnostics import ProjectGenerationError
from project_generation.generation.hardware import power_resource_compatibility
from project_generation.generation.models import GeneratedDeviceState, GeneratedGroup, GeneratedProject
from project_generation.generation.rules import StressPoint, matches

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
            assigned_groups: set[str] = set()
            for domain in state.power_domains:
                if len(domain.group_ids) != len(domain.group_names):
                    raise ProjectGenerationError(
                        f'Device state "{state.name}" power domain "{domain.name}" has mismatched group IDs and names',
                        code="generated_project.invalid_power_domain",
                        location=f"generated_project.device_states.{state.name}.power_domains.{domain.name}",
                        owner=state.name,
                    )
                if domain.assignment not in resources | pseudo_resources:
                    raise ProjectGenerationError(
                        f'Device state "{state.name}" uses unknown power resource "{domain.assignment}"',
                        code="generated_project.unknown_power_resource",
                        location=f"generated_project.device_states.{state.name}.power_domains.{domain.name}",
                        owner=state.name,
                    )
                self._validate_assignment_bias(state.name, domain.name, domain.assignment, domain.bias)
                if domain.assignment in resources:
                    resource = self.definition.power_resources[domain.assignment]
                    is_stress_bus = (resource.role or "").upper() == "STRESS" and not domain.group_ids
                    incompatibility = None if is_stress_bus else power_resource_compatibility(resource, domain.bias)
                    if incompatibility is not None:
                        raise ProjectGenerationError(
                            f'Device state "{state.name}" cannot assign power domain "{domain.name}" to '
                            f'"{domain.assignment}": {incompatibility}',
                            code="generated_project.incompatible_power_resource",
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
                    if group_name in assigned_groups:
                        raise ProjectGenerationError(
                            f'Device state "{state.name}" assigns group "{group_name}" to more than one power domain',
                            code="generated_project.duplicate_power_domain_group",
                            location=f"generated_project.device_states.{state.name}.power_domains.{domain.name}",
                            owner=state.name,
                        )
                    assigned_groups.add(group_name)

    @staticmethod
    def _validate_assignment_bias(state_name: str, domain_name: str, assignment: str, bias: Mapping[str, Any]) -> None:
        mode = str(bias.get("mode", "")).upper()
        if assignment == "GROUND" and mode != "GROUND":
            raise ProjectGenerationError(
                f'Device state "{state_name}" assigns power domain "{domain_name}" to GROUND with bias mode '
                f'"{mode or "<missing>"}"',
                code="generated_project.inconsistent_ground_bias",
                location=f"generated_project.device_states.{state_name}.power_domains.{domain_name}",
                owner=state_name,
            )
        if assignment == "FLOATING" and mode != "FLOATING":
            raise ProjectGenerationError(
                f'Device state "{state_name}" assigns power domain "{domain_name}" to FLOATING with bias mode '
                f'"{mode or "<missing>"}"',
                code="generated_project.inconsistent_floating_bias",
                location=f"generated_project.device_states.{state_name}.power_domains.{domain_name}",
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

            seen_groups: set[tuple[uuid.UUID, tuple[uuid.UUID, ...] | None]] = set()
            for test_group in plan.test_groups:
                group = groups_by_id.get(test_group.group_id)
                if group is None or group.name != test_group.group_name:
                    raise ProjectGenerationError(
                        f'Test plan "{plan.name}" references an unknown group "{test_group.group_name}"',
                        code="generated_project.invalid_test_group",
                        location=f"generated_project.test_plans.{plan.name}.test_groups",
                        owner=plan.name,
                    )
                subset = tuple(test_group.pin_ids) if test_group.pin_ids is not None else None
                key = (test_group.group_id, subset)
                if key in seen_groups:
                    raise ProjectGenerationError(
                        f'Test plan "{plan.name}" contains duplicate test group "{test_group.group_name}"',
                        code="generated_project.duplicate_test_group",
                        location=f"generated_project.test_plans.{plan.name}.test_groups",
                        owner=plan.name,
                    )
                seen_groups.add(key)
                if test_group.pin_ids is not None:
                    if not test_group.pin_ids:
                        raise ProjectGenerationError(
                            f'Test plan "{plan.name}" group "{test_group.group_name}" has an empty pin subset',
                            code="generated_project.empty_test_group_pin_subset",
                            location=f"generated_project.test_plans.{plan.name}.test_groups",
                            owner=plan.name,
                        )
                    unknown_pins = set(test_group.pin_ids) - set(group.pin_ids)
                    if unknown_pins:
                        raise ProjectGenerationError(
                            f'Test plan "{plan.name}" group "{test_group.group_name}" references pins outside the generated group',
                            code="generated_project.invalid_test_group_pin_subset",
                            location=f"generated_project.test_plans.{plan.name}.test_groups",
                            owner=plan.name,
                        )
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

