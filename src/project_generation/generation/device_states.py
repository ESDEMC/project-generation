import uuid
from collections.abc import Mapping
from typing import Any

from project_generation.definition.models import ProjectGenerationDefinition
from project_generation.diagnostics import (
    PowerResourceCandidateDiagnostic,
    PowerResourceResolutionError,
    PowerResourceResolutionIssue,
    ProjectGenerationError,
)
from project_generation.generation.ganging import get_ganging_policy, merge_bias_specs
from project_generation.generation.hardware import power_resource_compatibility
from project_generation.generation.models import GeneratedDeviceState, GeneratedGroup, GeneratedPowerDomain
from project_generation.generation.power_sequence import PowerSequenceResolver
from project_generation.generation.rules import matches
from project_generation.generation.values import merge_value_tree, resolve_value_tree

_PROJECT_GENERATION_NAMESPACE = uuid.UUID("b5cc252e-8608-4e8c-a03f-8ce6e5f55b43")
_PSEUDO_RESOURCES = {"GROUND", "FLOATING"}


class DeviceStateGenerator:
    def __init__(self, definition: ProjectGenerationDefinition, groups: list[GeneratedGroup]):
        self.definition = definition
        self.groups = groups
        self.groups_by_name = {group.name: group for group in groups}
        self.namespace = uuid.uuid5(_PROJECT_GENERATION_NAMESPACE, f"{definition.project.name}:device-states")
        self._resolved: dict[str, GeneratedDeviceState] = {}
        self._resolved_bias_specs: dict[str, dict[str, dict[str, Any]]] = {}
        self._resolving: set[str] = set()

    def generate(self) -> list[GeneratedDeviceState]:
        return [self._generate_state(name) for name in self.definition.device_states]

    def _generate_state(self, name: str) -> GeneratedDeviceState:
        if name in self._resolved:
            return self._resolved[name]
        if name in self._resolving:
            raise ProjectGenerationError(
                f'Circular device-state inheritance involving "{name}"',
                code="device_state.circular_inheritance",
                location=f"device_states.{name}.extends",
                owner=name,
            )

        try:
            state_definition = self.definition.device_states[name]
        except KeyError as error:
            raise ProjectGenerationError(
                f'Unknown device state "{name}"',
                code="device_state.unknown",
                location=f"device_states.{name}",
                owner=name,
            ) from error

        self._resolving.add(name)
        base_state = self._generate_state(state_definition.extends) if state_definition.extends else None

        base_bias_specs = self._resolved_bias_specs.get(state_definition.extends) if base_state else None
        bias_specs = self._resolve_bias_specs(state_definition, base_bias_specs)
        explicit_domains = self._resolve_explicit_domains(name, state_definition)
        power_domains = self._create_power_domains(
            state_name=name,
            state_definition=state_definition,
            bias_specs=bias_specs,
            explicit_domains=explicit_domains,
        )
        power_domains = self._add_stress_bus_domains(power_domains)

        generated = GeneratedDeviceState(
            id=uuid.uuid5(self.namespace, name),
            name=name,
            extends=state_definition.extends,
            power_domains=tuple(power_domains),
            power_on_sequence=PowerSequenceResolver.resolve(
                state_name=name,
                power_domains=power_domains,
                event="power_on",
                default_order="declaration",
            ),
            power_off_sequence=PowerSequenceResolver.resolve(
                state_name=name,
                power_domains=power_domains,
                event="power_off",
                default_order="reverse_power_on",
            ),
        )

        self._resolving.remove(name)
        self._resolved_bias_specs[name] = {group_name: dict(spec) for group_name, spec in bias_specs.items()}
        self._resolved[name] = generated
        return generated

    def _resolve_bias_specs(
        self,
        state_definition: Any,
        base_bias_specs: Mapping[str, Mapping[str, Any]] | None,
    ) -> dict[str, dict[str, Any]]:
        if base_bias_specs is None:
            bias_specs = {group.name: dict(group.bias_spec) for group in self.groups if group.bias_spec}
        else:
            bias_specs = {group_name: dict(spec) for group_name, spec in base_bias_specs.items()}
            for group in self.groups:
                bias_specs.setdefault(group.name, dict(group.bias_spec))

        for group in self.groups:
            context = {"group": group.context()}
            for rule in state_definition.rules:
                if not matches(rule.when, context):
                    continue
                resolved = resolve_value_tree(rule.set, context, definition=self.definition)
                unexpected = set(resolved) - {"bias_spec"}
                if unexpected:
                    names = ", ".join(sorted(unexpected))
                    raise ProjectGenerationError(
                        f'Device-state rule for group "{group.name}" sets unsupported fields: {names}. '
                        'Device-state rules may only set bias_spec.'
                    )
                if "bias_spec" in resolved:
                    spec = bias_specs.setdefault(group.name, {})
                    value = resolved["bias_spec"]
                    if not isinstance(value, Mapping):
                        raise ProjectGenerationError(
                            f'Device-state bias_spec for group "{group.name}" must resolve to an object'
                        )
                    merge_value_tree(spec, value)

        return {name: self._normalize_bias_spec(spec) for name, spec in bias_specs.items() if spec}

    @staticmethod
    def _normalize_bias_spec(spec: Mapping[str, Any]) -> dict[str, Any]:
        normalized = dict(spec)
        if "mode" not in normalized and "level" in normalized:
            normalized["mode"] = "VOLTAGE"
        if "mode" in normalized:
            normalized["mode"] = str(normalized["mode"]).upper()
        return normalized

    def _resolve_explicit_domains(self, state_name: str, state_definition: Any) -> list[GeneratedPowerDomain]:
        domains: list[GeneratedPowerDomain] = []
        for domain in state_definition.power_domains:
            missing = [group_name for group_name in domain.groups if group_name not in self.groups_by_name]
            if missing and not self.definition.groups.external:
                raise ProjectGenerationError(
                    f'Device state "{state_name}" power domain "{domain.name}" references unknown groups: '
                    f'{", ".join(missing)}'
                )
            groups = [self.groups_by_name[group_name] for group_name in domain.groups if group_name in self.groups_by_name]
            bias = self._normalize_bias_spec(resolve_value_tree(domain.bias.model_dump(), {}, definition=self.definition))
            self._validate_resource(state_name, domain.name, domain.assignment, bias)
            domains.append(
                GeneratedPowerDomain(
                    name=domain.name,
                    group_ids=tuple(group.id for group in groups),
                    group_names=tuple(domain.groups),
                    assignment=domain.assignment,
                    bias=bias,
                    timing=domain.timing.model_dump() if domain.timing else None,
                )
            )
        return domains

    def _create_power_domains(
        self,
        *,
        state_name: str,
        state_definition: Any,
        bias_specs: Mapping[str, Mapping[str, Any]],
        explicit_domains: list[GeneratedPowerDomain],
    ) -> list[GeneratedPowerDomain]:
        assigned_groups = {group_name for domain in explicit_domains for group_name in domain.group_names}
        remaining = {name: spec for name, spec in bias_specs.items() if name not in assigned_groups}
        if not remaining:
            return explicit_domains

        allocation = state_definition.allocation
        ganging_policy_name = allocation.ganging_policy if allocation else None
        try:
            ganging_policy = get_ganging_policy(ganging_policy_name)
        except ValueError as error:
            raise ProjectGenerationError(f'Device state "{state_name}" {error}') from error

        gangs = list(ganging_policy.gang(remaining))
        if allocation and allocation.strategy == "voltage_first":
            gangs.sort(key=lambda gang: self._voltage_sort_key(gang, remaining))
        elif allocation and allocation.strategy not in {None, "first_available", "voltage_first"}:
            raise ProjectGenerationError(
                f'Device state "{state_name}" has unsupported allocation strategy "{allocation.strategy}"'
            )

        reserved = set(allocation.reserve or []) if allocation else set()
        reserved.update(
            resource_name
            for resource_name, resource in self.definition.power_resources.items()
            if (resource.role or "").upper() == "STRESS"
        )
        used = {
            domain.assignment
            for domain in explicit_domains
            if domain.assignment not in _PSEUDO_RESOURCES
        }

        domains = list(explicit_domains)
        issues: list[PowerResourceResolutionIssue] = []
        for index, gang in enumerate(gangs, start=1):
            domain_groups = [self.groups_by_name[name] for name in gang if name in self.groups_by_name]
            bias = merge_bias_specs(*(remaining[group_name] for group_name in gang))
            assignment = self._pseudo_assignment(bias)
            if assignment is None:
                assignment = self._select_resource(
                    state_name=state_name,
                    group_names=gang,
                    bias=bias,
                    reserved=reserved,
                    used=used,
                    issues=issues,
                )
                if assignment is None:
                    continue
                used.add(assignment)

            domains.append(
                GeneratedPowerDomain(
                    name=self._automatic_domain_name(index, gang, domains),
                    group_ids=tuple(group.id for group in domain_groups),
                    group_names=tuple(gang),
                    assignment=assignment,
                    bias=bias,
                )
            )

        if issues:
            raise PowerResourceResolutionError(tuple(issues))
        return domains

    def _add_stress_bus_domains(self, power_domains: list[GeneratedPowerDomain]) -> list[GeneratedPowerDomain]:
        stress_resources = sorted(
            resource_name
            for resource_name, resource in self.definition.power_resources.items()
            if (resource.role or "").upper() == "STRESS"
        )
        assigned_resources = {domain.assignment for domain in power_domains}
        missing_resources = [resource for resource in stress_resources if resource not in assigned_resources]
        if not missing_resources:
            return power_domains

        domains = list(power_domains)
        existing_names = {domain.name for domain in domains}
        for resource_name in missing_resources:
            base_name = "stress_bus" if len(stress_resources) == 1 else f"stress_bus_{resource_name.lower()}"
            domain_name = base_name
            suffix = 2
            while domain_name in existing_names:
                domain_name = f"{base_name}_{suffix}"
                suffix += 1
            existing_names.add(domain_name)
            domains.append(
                GeneratedPowerDomain(
                    name=domain_name,
                    group_ids=(),
                    group_names=(),
                    assignment=resource_name,
                    bias={},
                )
            )
        return domains

    @staticmethod
    def _voltage_sort_key(gang: tuple[str, ...], bias_specs: Mapping[str, Mapping[str, Any]]) -> tuple[float, str]:
        bias = merge_bias_specs(*(bias_specs[name] for name in gang))
        return -abs(float(bias.get("level", 0.0) or 0.0)), gang[0]

    @staticmethod
    def _pseudo_assignment(bias: Mapping[str, Any]) -> str | None:
        mode = str(bias.get("mode", "")).upper()
        return mode if mode in _PSEUDO_RESOURCES else None

    def _select_resource(
        self,
        *,
        state_name: str,
        group_names: tuple[str, ...],
        bias: Mapping[str, Any],
        reserved: set[str],
        used: set[str],
        issues: list[PowerResourceResolutionIssue],
    ) -> str | None:
        for resource_name, resource in sorted(self.definition.power_resources.items()):
            if (resource.role or "BIAS").upper() != "BIAS" or resource_name in reserved or resource_name in used:
                continue
            if power_resource_compatibility(resource, bias) is None:
                return resource_name

        candidates: list[PowerResourceCandidateDiagnostic] = []
        for resource_name, resource in sorted(self.definition.power_resources.items()):
            if (resource.role or "BIAS").upper() != "BIAS":
                reason = f'role is "{(resource.role or "BIAS").upper()}", not "BIAS"'
            elif resource_name in reserved:
                reason = "reserved for stress or allocation policy"
            elif resource_name in used:
                reason = "already assigned to another power domain"
            else:
                reason = power_resource_compatibility(resource, bias)
            candidates.append(
                PowerResourceCandidateDiagnostic(
                    resource=resource_name,
                    accepted=reason is None,
                    reason=reason,
                )
            )

        issues.append(
            PowerResourceResolutionIssue(
                state_name=state_name,
                group_name=", ".join(group_names),
                bias=dict(bias),
                candidates=tuple(candidates),
            )
        )
        return None

    def _validate_resource(self, state_name: str, domain_name: str, assignment: str, bias: Mapping[str, Any]) -> None:
        if assignment in _PSEUDO_RESOURCES:
            expected_mode = assignment
            actual_mode = str(bias.get("mode", "")).upper()
            if actual_mode != expected_mode:
                raise ProjectGenerationError(
                    f'Device state "{state_name}" power domain "{domain_name}" assigns {assignment} '
                    f'with bias mode "{actual_mode or "<missing>"}"'
                )
            return
        if assignment not in self.definition.power_resources:
            raise ProjectGenerationError(
                f'Device state "{state_name}" power domain "{domain_name}" references unknown power resource '
                f'"{assignment}"'
            )
        reason = power_resource_compatibility(self.definition.power_resources[assignment], bias)
        if reason is not None:
            raise PowerResourceResolutionError(
                (
                    PowerResourceResolutionIssue(
                        state_name=state_name,
                        group_name=domain_name,
                        bias=dict(bias),
                        requested_resource=assignment,
                        candidates=(
                            PowerResourceCandidateDiagnostic(
                                resource=assignment,
                                accepted=False,
                                reason=reason,
                            ),
                        ),
                    ),
                )
            )

    @staticmethod
    def _automatic_domain_name(
        index: int,
        group_names: tuple[str, ...],
        existing: list[GeneratedPowerDomain],
    ) -> str:
        base = "_".join(group_names) or f"domain_{index}"
        existing_names = {domain.name for domain in existing}
        if base not in existing_names:
            return base
        suffix = 2
        while f"{base}_{suffix}" in existing_names:
            suffix += 1
        return f"{base}_{suffix}"
