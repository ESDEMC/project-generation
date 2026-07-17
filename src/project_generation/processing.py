import copy
import itertools
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Iterable, Mapping

from project_generation.models import DimensionDefinition, OverrideDefinition, TestPlanRuleDefinition


@dataclass(frozen=True, kw_only=True)
class GroupRecord:
    name: str
    group_type: str
    parameters: Mapping[str, Any] = field(default_factory=dict)

    def context(self) -> dict[str, Any]:
        return {"name": self.name, "group_type": self.group_type, **dict(self.parameters)}


@dataclass(frozen=True, kw_only=True)
class GroupPartition:
    groups: tuple[GroupRecord, ...]
    values: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, kw_only=True)
class TestPlanCandidate:
    rule_id: str
    partition: GroupPartition
    dimensions: Mapping[str, Any]
    values: Mapping[str, Any]
    excluded: bool = False


@dataclass(frozen=True, kw_only=True)
class StressPoint:
    values: Mapping[str, Any]


def expand_dimensions(dimensions: Iterable[DimensionDefinition]) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    dimensions = list(dimensions)
    if not dimensions:
        return [({}, {})]
    combinations: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for selected in itertools.product(*(dimension.values for dimension in dimensions)):
        context: dict[str, Any] = {}
        values: dict[str, Any] = {}
        for dimension, selected_value in zip(dimensions, selected, strict=True):
            context[dimension.name] = selected_value.value
            deep_merge(values, expand_dotted_keys(selected_value.set))
        combinations.append((context, values))
    return combinations


def partition_groups(rule: TestPlanRuleDefinition, groups: Iterable[GroupRecord]) -> list[GroupPartition]:
    selected = [group for group in groups if matches(rule.groups.select.where, {"group": group.context(), **group.context()})]
    partition = rule.groups.partition
    if partition.mode == "each":
        return [GroupPartition(groups=(group,), values=group.context()) for group in selected]
    if partition.mode == "all":
        return [GroupPartition(groups=tuple(selected), values={})] if selected else []

    buckets: dict[tuple[Any, ...], list[GroupRecord]] = {}
    for group in selected:
        context = group.context()
        key = tuple(resolve_path(context, field) for field in partition.fields)
        buckets.setdefault(key, []).append(group)
    return [
        GroupPartition(groups=tuple(bucket), values=dict(zip(partition.fields, key, strict=True)))
        for key, bucket in buckets.items()
    ]


def expand_rule(rule: TestPlanRuleDefinition, groups: Iterable[GroupRecord]) -> list[TestPlanCandidate]:
    candidates: list[TestPlanCandidate] = []
    for partition in partition_groups(rule, groups):
        for dimensions, dimension_values in expand_dimensions(rule.dimensions):
            values = expand_dotted_keys(copy.deepcopy(rule.template))
            deep_merge(values, dimension_values)
            excluded = False
            plan_context = _candidate_context(partition, dimensions, values)
            for override in rule.overrides:
                if override.scope.value != "plan":
                    continue
                if matches(override.when, plan_context):
                    deep_merge(values, expand_dotted_keys(override.set))
                    excluded = excluded or override.exclude
                    plan_context = _candidate_context(partition, dimensions, values)
            candidates.append(
                TestPlanCandidate(
                    rule_id=rule.id,
                    partition=partition,
                    dimensions=dimensions,
                    values=values,
                    excluded=excluded,
                )
            )
    return candidates


def resolve_group_values(candidate: TestPlanCandidate, group: GroupRecord, overrides: Iterable[OverrideDefinition]) -> dict[str, Any]:
    values, _ = resolve_group_values_and_exclusion(candidate, group, overrides)
    return values


def resolve_group_values_and_exclusion(
    candidate: TestPlanCandidate,
    group: GroupRecord,
    overrides: Iterable[OverrideDefinition],
) -> tuple[dict[str, Any], bool]:
    values = copy.deepcopy(dict(candidate.values))
    excluded = False
    context = _candidate_context(candidate.partition, candidate.dimensions, values, group)
    for override in overrides:
        if override.scope.value != "group":
            continue
        if matches(override.when, context):
            deep_merge(values, expand_dotted_keys(override.set))
            excluded = excluded or override.exclude
            context = _candidate_context(candidate.partition, candidate.dimensions, values, group)
    return values, excluded


def candidate_context(
    candidate: TestPlanCandidate,
    *,
    values: Mapping[str, Any] | None = None,
    group: GroupRecord | None = None,
) -> dict[str, Any]:
    return _candidate_context(candidate.partition, candidate.dimensions, values or candidate.values, group)


def expand_stress_parameters(definitions: Mapping[str, Any], context: Mapping[str, Any]) -> list[StressPoint]:
    resolved = {name: resolve_parameter_series(value, context) for name, value in definitions.items()}
    lengths = {len(value) for value in resolved.values() if isinstance(value, list)}
    if len(lengths) > 1:
        raise ValueError(f"Stress parameter series lengths must match; received {sorted(lengths)}")
    point_count = next(iter(lengths), 1)
    points: list[StressPoint] = []
    for index in range(point_count):
        point = {name: value[index] if isinstance(value, list) else value for name, value in resolved.items()}
        points.append(StressPoint(values=point))
    return points


def resolve_parameter_series(definition: Any, context: Mapping[str, Any]) -> Any:
    if not isinstance(definition, dict):
        return definition
    if "values" in definition:
        return list(definition["values"])
    if "range" in definition:
        return generate_range(definition["range"])
    if "from" not in definition:
        return definition

    base = resolve_path(context, definition["from"])
    modes = [key for key in ("add", "multiply_by", "offset_range", "factor_range") if key in definition]
    if len(modes) != 1:
        raise ValueError("A relative stress series must define exactly one operation")
    mode = modes[0]
    operand = definition[mode]
    if mode == "add":
        values = operand if isinstance(operand, list) else [operand]
        return [base + value for value in values]
    if mode == "multiply_by":
        values = operand if isinstance(operand, list) else [operand]
        return [base * value for value in values]
    range_values = generate_range(operand)
    if mode == "offset_range":
        return [base + value for value in range_values]
    return [base * value for value in range_values]


def generate_range(definition: Mapping[str, Any]) -> list[float]:
    start = float(definition["start"])
    stop = float(definition["stop"])
    has_step = "step" in definition
    has_num = "num" in definition
    if has_step == has_num:
        raise ValueError("Range requires exactly one of step or num")
    if has_num:
        num = int(definition["num"])
        if num <= 0:
            raise ValueError("Range num must be positive")
        if num == 1:
            return [start]
        return [start + ((stop - start) * index / (num - 1)) for index in range(num)]

    step = float(definition["step"])
    if step == 0:
        raise ValueError("Range step must not be zero")
    if (stop - start) * step < 0:
        raise ValueError("Range step points away from stop")
    decimal_start = Decimal(str(start))
    decimal_stop = Decimal(str(stop))
    decimal_step = Decimal(str(step))
    result: list[float] = []
    current = decimal_start
    compare = (lambda value: value <= decimal_stop) if decimal_step > 0 else (lambda value: value >= decimal_stop)
    while compare(current):
        result.append(float(current))
        current += decimal_step
    return result


def matches(conditions: Mapping[str, Any], context: Mapping[str, Any]) -> bool:
    for path, expected in conditions.items():
        actual = resolve_path(context, path)
        if isinstance(expected, dict):
            if "equals" in expected and actual != expected["equals"]:
                return False
            if "not_equals" in expected and actual == expected["not_equals"]:
                return False
            if "in" in expected and actual not in expected["in"]:
                return False
            if "exists" in expected and (actual is not None) != bool(expected["exists"]):
                return False
        elif actual != expected:
            return False
    return True


def resolve_path(context: Mapping[str, Any], path: str) -> Any:
    current: Any = context
    for part in path.split("."):
        if isinstance(current, Mapping):
            if part not in current:
                return None
            current = current[part]
        else:
            return None
    return current


def expand_dotted_keys(values: Mapping[str, Any]) -> dict[str, Any]:
    expanded: dict[str, Any] = {}
    for key, value in values.items():
        if isinstance(value, dict):
            value = expand_dotted_keys(value)
        current = expanded
        parts = key.split(".")
        for part in parts[:-1]:
            current = current.setdefault(part, {})
        current[parts[-1]] = value
    return expanded


def deep_merge(target: dict[str, Any], source: Mapping[str, Any]) -> dict[str, Any]:
    for key, value in source.items():
        if isinstance(value, Mapping) and isinstance(target.get(key), dict):
            deep_merge(target[key], value)
        else:
            target[key] = copy.deepcopy(value)
    return target


def _candidate_context(
    partition: GroupPartition,
    dimensions: Mapping[str, Any],
    values: Mapping[str, Any],
    group: GroupRecord | None = None,
) -> dict[str, Any]:
    singular = group or (partition.groups[0] if len(partition.groups) == 1 else None)
    return {
        **dict(dimensions),
        "group": singular.context() if singular else {},
        "partition": dict(partition.values),
        "plan": dict(values),
    }
