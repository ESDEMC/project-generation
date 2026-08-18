import json
import pathlib
import uuid
from dataclasses import fields, is_dataclass
from typing import Any, Mapping

from project_generation.generation.models import GeneratedProject


def generated_project_to_dict(project: GeneratedProject) -> dict[str, Any]:
    value = _to_json_value(project)
    if not isinstance(value, dict):
        raise TypeError("GeneratedProject did not serialize to an object")
    return value


def generated_project_to_json(project: GeneratedProject, *, indent: int | None = 2) -> str:
    return json.dumps(generated_project_to_dict(project), indent=indent, sort_keys=False)


def write_generated_project(project: GeneratedProject, path: str | pathlib.Path, *, indent: int | None = 2) -> None:
    pathlib.Path(path).write_text(generated_project_to_json(project, indent=indent) + "\n", encoding="utf-8")


def _to_json_value(value: Any) -> Any:
    if isinstance(value, uuid.UUID):
        return str(value)
    if is_dataclass(value) and not isinstance(value, type):
        return {item.name: _to_json_value(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, Mapping):
        return {str(key): _to_json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_to_json_value(item) for item in value]
    return value
