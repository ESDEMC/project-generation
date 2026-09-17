import uuid
from collections.abc import Iterable, Mapping
from typing import Any

from project_generation.definition.models import ExplicitGroupDefinition, GroupGenerationRule, ProjectGenerationDefinition
from project_generation.diagnostics import ProjectGenerationError
from project_generation.generation.models import GeneratedGroup, GeneratedPin
from project_generation.generation.rules import matches
from project_generation.generation.values import (
    build_partition_context,
    render_group_name,
    resolve_group_by_value,
    resolve_value_tree,
)

_PROJECT_GENERATION_NAMESPACE = uuid.UUID("b5cc252e-8608-4e8c-a03f-8ce6e5f55b43")


class GroupGenerator:
    def __init__(self, definition: ProjectGenerationDefinition, pins: list[GeneratedPin]):
        self.definition = definition
        self.pins = pins
        self.namespace = uuid.uuid5(_PROJECT_GENERATION_NAMESPACE, f"{definition.project.name}:groups")

    def generate(self) -> list[GeneratedGroup]:
        groups = list(self.iter_generate())
        self._validate_unique_names(groups)
        return groups

    def generate_best_effort(self) -> tuple[list[GeneratedGroup], ProjectGenerationError | None]:
        groups: list[GeneratedGroup] = []
        try:
            for group in self.iter_generate():
                groups.append(group)
            self._validate_unique_names(groups)
        except ProjectGenerationError as error:
            return groups, error
        except Exception as error:
            return groups, ProjectGenerationError(str(error), code="group.generation_failed")
        return groups, None

    def iter_generate(self):
        if self.definition.groups.external:
            return

        by_designator = {pin.designator: pin for pin in self.pins}
        for group in self.definition.groups.explicit:
            yield self._compile_explicit_group(group, by_designator)
        for rule in self.definition.groups.generation:
            yield from self._iter_rule(rule)

    @staticmethod
    def _validate_unique_names(groups: list[GeneratedGroup]) -> None:
        names = [group.name for group in groups]
        duplicates = sorted({name for name in names if names.count(name) > 1})
        if duplicates:
            raise ProjectGenerationError(f"Duplicate generated group names: {', '.join(duplicates)}")

    def _compile_explicit_group(
        self,
        definition: ExplicitGroupDefinition,
        by_designator: Mapping[str, GeneratedPin],
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
            id=uuid.uuid5(self.namespace, definition.name),
            name=definition.name,
            group_type=definition.group_type,
            pin_ids=tuple(by_designator[designator].id for designator in definition.pins),
            bias_spec=dict(definition.bias_spec or {}),
            parameters=dict(definition.parameters or {}),
        )

    def _compile_rule(self, rule: GroupGenerationRule) -> list[GeneratedGroup]:
        return list(self._iter_rule(rule))

    def _iter_rule(self, rule: GroupGenerationRule):
        selected = [pin for pin in self.pins if matches(rule.select.where, pin.context())]
        buckets: dict[tuple[Any, ...], list[GeneratedPin]] = {}
        for pin in selected:
            pin_context = pin.context()
            key = tuple(resolve_group_by_value(field, pin_context, rule.id) for field in rule.group_by)
            buckets.setdefault(key, []).append(pin)

        for key, bucket in buckets.items():
            partition = build_partition_context(rule.group_by, key)
            context = {
                "partition": partition,
                "members": [pin.context() for pin in bucket],
            }
            values = resolve_value_tree(rule.set, context, definition=self.definition)
            name = render_group_name(self.definition, rule, context)
            group_type = values.pop("group_type", None)
            if group_type is None:
                raise ProjectGenerationError(f'Group rule "{rule.id}" did not resolve group_type')
            bias_spec = values.pop("bias_spec", {})
            parameters = values.pop("parameters", {})
            if values:
                parameters = {**parameters, **values}
            yield GeneratedGroup(
                    id=uuid.uuid5(self.namespace, name),
                    name=name,
                    group_type=str(group_type),
                    pin_ids=tuple(pin.id for pin in bucket),
                    bias_spec=bias_spec,
                    parameters=parameters,
                    generation_rule_id=rule.id,
                )
