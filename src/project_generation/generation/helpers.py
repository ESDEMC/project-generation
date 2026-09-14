import re
from typing import Any, Mapping

from project_generation.definition.models import (
    FormatterDefinition,
    GroupByFieldDefinition,
    NameTemplateDefinition,
    ProjectGenerationDefinition,
)
from project_generation.diagnostics import ProjectGenerationError
from project_generation.generation.rules import matches, resolve_path

_TEMPLATE_FIELD = re.compile(r"\{([^{}]+)\}")
_OMIT = object()


def normalize_definition_value(value: Any) -> Any:
    if hasattr(value, "root") and type(value).__name__.endswith("Definition"):
        return normalize_definition_value(value.root)
    if hasattr(value, "model_dump"):
        return value.model_dump(by_alias=True, exclude_unset=True)
    return value

def get_aliased_field_value(model: Any, alias: str) -> Any:
    attribute_name = f"{alias}_"
    if hasattr(model, attribute_name):
        return getattr(model, attribute_name)
    if hasattr(model, alias):
        return getattr(model, alias)
    if hasattr(model, "model_dump"):
        values = model.model_dump(by_alias=True)
        if alias in values:
            return values[alias]
    raise ProjectGenerationError(f'Model {type(model).__name__} does not define field "{alias}"')

def group_by_source(field: str | GroupByFieldDefinition) -> str:
    if isinstance(field, str):
        return field
    return field.source

def resolve_group_by_value(
    field: str | GroupByFieldDefinition,
    context: Mapping[str, Any],
    rule_id: str,
) -> Any:
    if not isinstance(field, str) and field.when is not None and not matches(field.when, context):
        return _OMITTED_GROUP_BY_VALUE
    return resolve_required_path(context, group_by_source(field), f'group rule "{rule_id}"')

def build_partition_context(
    fields: list[str | GroupByFieldDefinition],
    key: tuple[Any, ...],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for field, value in zip(fields, key, strict=True):
        if value is _OMITTED_GROUP_BY_VALUE:
            continue
        set_path(result, group_by_source(field), value)
    return result

def resolve_value_tree(
    value: Any,
    context: Mapping[str, Any],
    *,
    definition: ProjectGenerationDefinition | None = None,
) -> Any:
    value = normalize_definition_value(value)

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
    normalized = [normalize_definition_value(item) for item in value]
    if not normalized or not all(isinstance(item, Mapping) and is_value_definition(item) for item in normalized):
        return False
    value[:] = normalized
    return any("when" in item for item in normalized)

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
        when = getattr(field, "when", None)
        if when is not None and not matches(when, context):
            values[field_name] = ""
            continue

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
