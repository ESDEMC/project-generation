import re
from collections import Counter
from typing import Any

from project_generation.diagnostics import DiagnosticSeverity, GenerationDiagnostic, GenerationDiagnostics
from project_generation.definition.models import ProjectGenerationDefinition

_TEMPLATE_FIELD = re.compile(r"\{([^{}|]+)(?:\|[^{}]+)?\}")


def validate_project_definition(definition: ProjectGenerationDefinition) -> GenerationDiagnostics:
    diagnostics = GenerationDiagnostics()
    _validate_named_references(definition, diagnostics)
    _validate_rules(definition, diagnostics)
    _validate_state_inheritance(definition, diagnostics)
    return diagnostics


def _error(diagnostics: GenerationDiagnostics, code: str, message: str, location: str) -> None:
    diagnostics.append(GenerationDiagnostic(severity=DiagnosticSeverity.ERROR, code=code, message=message, location=location))


def _warning(diagnostics: GenerationDiagnostics, code: str, message: str, location: str) -> None:
    diagnostics.append(GenerationDiagnostic(severity=DiagnosticSeverity.WARNING, code=code, message=message, location=location))


def _validate_named_references(definition: ProjectGenerationDefinition, diagnostics: GenerationDiagnostics) -> None:
    if definition.dut and isinstance(definition.dut.pins.source, str) and definition.dut.pins.source not in definition.sources:
        _error(diagnostics, "SOURCE_NOT_FOUND", f'Unknown source "{definition.dut.pins.source}".', "dut.pins.source")

    for rule_index, rule in enumerate(definition.groups.generation):
        for field_name, field_definition in rule.name.fields.items():
            if field_definition.mapping and field_definition.mapping not in definition.mappings:
                _error(
                    diagnostics,
                    "MAPPING_NOT_FOUND",
                    f'Unknown mapping "{field_definition.mapping}".',
                    f"groups.generation[{rule_index}].name.fields.{field_name}.mapping",
                )
            if field_definition.formatter and field_definition.formatter not in definition.formatters:
                _error(
                    diagnostics,
                    "FORMATTER_NOT_FOUND",
                    f'Unknown formatter "{field_definition.formatter}".',
                    f"groups.generation[{rule_index}].name.fields.{field_name}.formatter",
                )

    for state_name, state in definition.device_states.items():
        if state.extends and state.extends not in definition.device_states:
            _error(diagnostics, "DEVICE_STATE_NOT_FOUND", f'Unknown device state "{state.extends}".', f"device_states.{state_name}.extends")
        if state.allocation:
            for resource in state.allocation.reserve:
                if definition.hardware is None and resource not in definition.power_resources:
                    _error(
                        diagnostics,
                        "POWER_RESOURCE_NOT_FOUND",
                        f'Unknown power resource "{resource}".',
                        f"device_states.{state_name}.allocation.reserve",
                    )
        for domain_index, domain in enumerate(state.power_domains):
            if definition.hardware is None and domain.assignment not in definition.power_resources and domain.assignment != "GROUND":
                _error(
                    diagnostics,
                    "POWER_RESOURCE_NOT_FOUND",
                    f'Unknown power resource "{domain.assignment}".',
                    f"device_states.{state_name}.power_domains[{domain_index}].assignment",
                )

    for plan_index, plan in enumerate(definition.test_plans):
        if plan.device_state and plan.device_state not in definition.device_states:
            _error(
                diagnostics,
                "DEVICE_STATE_NOT_FOUND",
                f'Unknown device state "{plan.device_state}".',
                f"test_plans[{plan_index}].device_state",
            )


def _validate_rules(definition: ProjectGenerationDefinition, diagnostics: GenerationDiagnostics) -> None:
    rule_ids = [rule.id for rule in definition.test_plan_generation.rules]
    for duplicate, count in Counter(rule_ids).items():
        if count > 1:
            _error(diagnostics, "RULE_ID_DUPLICATE", f'Rule id "{duplicate}" is declared {count} times.', "test_plan_generation.rules")

    for rule_index, rule in enumerate(definition.test_plan_generation.rules):
        dimensions = {dimension.name for dimension in rule.dimensions}
        for dimension_index, dimension in enumerate(rule.dimensions):
            for value_index, value in enumerate(dimension.values):
                set_values = value.set if hasattr(value, "set") else {}
                state_name = _find_path(set_values, "device_state")
                if isinstance(state_name, str) and state_name not in definition.device_states:
                    _error(
                        diagnostics,
                        "DEVICE_STATE_NOT_FOUND",
                        f'Unknown device state "{state_name}".',
                        f"test_plan_generation.rules[{rule_index}].dimensions[{dimension_index}].values[{value_index}].set.device_state",
                    )

        template_state = _find_path(rule.template, "device_state")
        if isinstance(template_state, str) and template_state not in definition.device_states:
            _error(
                diagnostics,
                "DEVICE_STATE_NOT_FOUND",
                f'Unknown device state "{template_state}".',
                f"test_plan_generation.rules[{rule_index}].template.device_state",
            )

        for override_index, override in enumerate(rule.overrides):
            for key in override.when:
                root = key.split(".", 1)[0]
                if root in {"group", "partition", "plan"}:
                    continue
                if root not in dimensions:
                    _error(
                        diagnostics,
                        "OVERRIDE_DIMENSION_NOT_FOUND",
                        f'Override references undeclared dimension "{root}".',
                        f"test_plan_generation.rules[{rule_index}].overrides[{override_index}].when.{key}",
                    )
            state_name = _find_path(override.set, "device_state")
            if isinstance(state_name, str) and state_name not in definition.device_states:
                _error(
                    diagnostics,
                    "DEVICE_STATE_NOT_FOUND",
                    f'Unknown device state "{state_name}".',
                    f"test_plan_generation.rules[{rule_index}].overrides[{override_index}].set.device_state",
                )

        name_definition = rule.template.get("name")
        if isinstance(name_definition, dict):
            template = name_definition.get("template")
            named_fields = name_definition.get("fields", {})
            if isinstance(named_fields, dict):
                for field_name, field_definition in named_fields.items():
                    if not isinstance(field_definition, dict):
                        continue
                    mapping_name = field_definition.get("mapping")
                    formatter_name = field_definition.get("formatter")
                    source = field_definition.get("source")
                    if mapping_name and mapping_name not in definition.mappings:
                        _error(
                            diagnostics,
                            "MAPPING_NOT_FOUND",
                            f'Unknown mapping "{mapping_name}".',
                            f"test_plan_generation.rules[{rule_index}].template.name.fields.{field_name}.mapping",
                        )
                    if formatter_name and formatter_name not in definition.formatters:
                        _error(
                            diagnostics,
                            "FORMATTER_NOT_FOUND",
                            f'Unknown formatter "{formatter_name}".',
                            f"test_plan_generation.rules[{rule_index}].template.name.fields.{field_name}.formatter",
                        )
                    if isinstance(source, str) and rule.groups.partition.mode != "each" and source.startswith("group."):
                        _error(
                            diagnostics,
                            "SINGULAR_GROUP_CONTEXT_UNAVAILABLE",
                            "A singular group name field is only valid for partition mode 'each'.",
                            f"test_plan_generation.rules[{rule_index}].template.name.fields.{field_name}.source",
                        )

            if isinstance(template, str) and not named_fields:
                fields = set(_TEMPLATE_FIELD.findall(template))
                if rule.groups.partition.mode != "each" and any(field.startswith("group.") for field in fields):
                    _error(
                        diagnostics,
                        "SINGULAR_GROUP_CONTEXT_UNAVAILABLE",
                        "A singular group name field is only valid for partition mode 'each'.",
                        f"test_plan_generation.rules[{rule_index}].template.name.template",
                    )
                for field in fields:
                    root = field.split(".", 1)[0]
                    if root not in dimensions | {"group", "partition", "plan"}:
                        _warning(
                            diagnostics,
                            "TEMPLATE_FIELD_UNRESOLVED",
                            f'Template field "{field}" is not a declared dimension or standard context.',
                            f"test_plan_generation.rules[{rule_index}].template.name.template",
                        )


def _validate_state_inheritance(definition: ProjectGenerationDefinition, diagnostics: GenerationDiagnostics) -> None:
    for start in definition.device_states:
        seen: list[str] = []
        current: str | None = start
        while current:
            if current in seen:
                cycle = " -> ".join([*seen, current])
                _error(diagnostics, "DEVICE_STATE_INHERITANCE_CYCLE", f"Device state inheritance cycle: {cycle}.", f"device_states.{start}")
                break
            seen.append(current)
            state = definition.device_states.get(current)
            current = state.extends if state else None


def _find_path(values: dict[str, Any], path: str) -> Any:
    if path in values:
        return values[path]
    current: Any = values
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current
