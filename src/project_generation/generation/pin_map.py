from collections.abc import Mapping, Sequence
from pathlib import Path
import string
from typing import Any

from project_generation.definition.models import PinMapDefinition, ProjectGenerationDefinition
from project_generation.diagnostics import ProjectGenerationError
from project_generation.generation.models import GeneratedPin, GeneratedPinMapEntry
from project_generation.generation.rules import resolve_path
from project_generation.generation.sources import load_source_records


def generate_pin_map(
    definition: ProjectGenerationDefinition,
    pins: Sequence[GeneratedPin],
    *,
    base_directory: Path,
) -> tuple[GeneratedPinMapEntry, ...]:
    config = definition.pin_map
    if config is None:
        return ()

    mapping_tables = _load_mapping_tables(definition, config, base_directory)
    entries: list[GeneratedPinMapEntry] = []
    for pin in pins:
        location = resolve_path(pin.context(), config.location)
        if location is None:
            raise ProjectGenerationError(
                f'Pin "{pin.designator}" does not define pin-map location "{config.location}"',
                code="pin_map.location_missing",
                location=f"pins.{pin.designator}",
                context={"designator": pin.designator, "path": config.location},
            )
        location = str(location)
        for mapping, table in mapping_tables:
            try:
                location = table[location]
            except KeyError as error:
                raise ProjectGenerationError(
                    f'Pin-map location "{location}" for pin "{pin.designator}" was not found in source "{mapping.source}"',
                    code="pin_map.mapping_missing",
                    location=f"pin_map.mappings.{mapping.source}",
                    context={"designator": pin.designator, "location": location, "source": mapping.source},
                ) from error
        entries.append(GeneratedPinMapEntry(pin=pin.designator, location=location))
    return tuple(entries)


def _load_mapping_tables(
    definition: ProjectGenerationDefinition,
    config: PinMapDefinition,
    base_directory: Path,
) -> list[tuple[Any, dict[str, str]]]:
    result = []
    for mapping in config.mappings or []:
        try:
            source = definition.sources[mapping.source]
        except KeyError as error:
            raise ProjectGenerationError(
                f'Unknown pin-map source "{mapping.source}"',
                code="pin_map.source_unknown",
                location="pin_map.mappings",
            ) from error
        if _has_unbound_directive(getattr(source, "path", None)):
            if mapping.on_missing == "identity":
                continue
            raise ProjectGenerationError(
                f'Pin-map source "{mapping.source}" has not been bound to an input file',
                code="pin_map.mapping_input_missing",
                location=f"pin_map.mappings.{mapping.source}",
            )
        records = load_source_records(
            source,
            base_directory=base_directory,
            mappings=definition.mappings,
            formatters=definition.formatters,
        )
        table: dict[str, str] = {}
        for index, record in enumerate(records):
            source_value = resolve_path(record, mapping.from_)
            target_value = resolve_path(record, mapping.to)
            if source_value is None or target_value is None:
                raise ProjectGenerationError(
                    f'Pin-map source "{mapping.source}" record {index} must define "{mapping.from_}" and "{mapping.to}"',
                    code="pin_map.mapping_invalid",
                    location=f"sources.{mapping.source}",
                )
            key = str(source_value)
            if key in table:
                raise ProjectGenerationError(
                    f'Pin-map source "{mapping.source}" contains duplicate location "{key}"',
                    code="pin_map.mapping_duplicate",
                    location=f"sources.{mapping.source}",
                )
            table[key] = str(target_value)
        result.append((mapping, table))
    return result


def _has_unbound_directive(path: str | None) -> bool:
    if not path:
        return False
    return any(field_name for _, field_name, _, _ in string.Formatter().parse(path))
