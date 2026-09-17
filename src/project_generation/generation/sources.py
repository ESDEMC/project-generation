import csv
import json
import pathlib
from collections.abc import Mapping
from typing import Any

from project_generation.definition.models import (
    CsvSource,
    ExcelSource,
    FormatterDefinition,
    InlineSource,
    JsonSource,
    SourceDefinition,
    SourceFieldMapping,
)
from project_generation.diagnostics import ProjectGenerationError
from project_generation.generation.values import apply_formatter, get_aliased_field_value, resolve_required_path, set_path


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
            scale = None
        else:
            source_path = get_aliased_field_value(field_mapping, "from")
            value_mapping_name = field_mapping.mapping
            formatter_name = field_mapping.formatter
            scale = field_mapping.scale

        value = resolve_required_path(record, source_path, "source mapping")
        if value_mapping_name:
            try:
                value = (mappings or {})[value_mapping_name][str(value)]
            except KeyError as error:
                raise ProjectGenerationError(
                    f'Value "{value}" is not present in mapping "{value_mapping_name}"'
                ) from error
        if scale is not None:
            try:
                value = float(value) * scale
            except (TypeError, ValueError) as error:
                raise ProjectGenerationError(
                    f'Source field "{source_path}" with value {value!r} cannot be scaled by {scale:g}'
                ) from error
        if formatter_name:
            try:
                formatter = (formatters or {})[formatter_name]
            except KeyError as error:
                raise ProjectGenerationError(f'Unknown formatter "{formatter_name}"') from error
            value = apply_formatter(value, formatter)
        set_path(result, target, value)
    return result
