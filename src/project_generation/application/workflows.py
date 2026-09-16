import pathlib
import string
from collections.abc import Mapping

from project_generation.diagnostics import GenerationDiagnostics, ProjectGenerationError
from project_generation.definition.models import ProjectGenerationDefinition


def raise_for_diagnostics(diagnostics: GenerationDiagnostics) -> None:
    """Raise one public exception when semantic validation reports errors."""
    if not diagnostics.has_errors:
        return
    formatted = "\n".join(item.format() for item in diagnostics)
    raise ProjectGenerationError(
        f"Project generation definition is invalid:\n{formatted}",
        code="definition.invalid",
        context={"diagnostics": [item.format() for item in diagnostics]},
    )


def replace_source_paths(
    definition: ProjectGenerationDefinition,
    replacements: Mapping[str, str | pathlib.Path],
) -> ProjectGenerationDefinition:
    """Return a copy of a definition with selected file-source paths replaced.

    This is source-name based replacement. For definitions that intentionally use
    path format directives such as ``{input_file}``, prefer :func:`bind_input_files`.
    """
    unknown = sorted(set(replacements) - set(definition.sources))
    if unknown:
        raise KeyError(f"Unknown source names: {', '.join(unknown)}")

    sources = dict(definition.sources)
    for name, replacement in replacements.items():
        source = sources[name]
        if not hasattr(source, "path"):
            raise TypeError(f'Source "{name}" is not a file-backed source')
        sources[name] = source.model_copy(update={"path": str(pathlib.Path(replacement))})
    return definition.model_copy(update={"sources": sources})


def source_path_directives(definition: ProjectGenerationDefinition) -> tuple[str, ...]:
    """Return unique ``str.format`` field names used by file-backed source paths."""
    formatter = string.Formatter()
    directives: list[str] = []
    for source in definition.sources.values():
        source_path = getattr(source, "path", None)
        if not source_path:
            continue
        for _, field_name, _, _ in formatter.parse(source_path):
            if field_name and field_name not in directives:
                directives.append(field_name)
    return tuple(directives)


def bind_input_files(
    definition: ProjectGenerationDefinition,
    bindings: Mapping[str, str | pathlib.Path],
) -> ProjectGenerationDefinition:
    """Format file-backed source paths using named input-file bindings.

    A definition can declare a reusable input directive, for example::

        sources:
          project:
            type: json
            path: '{input_file}'
          pins:
            type: json
            path: '{input_file}'

    ``bind_input_files(definition, {"input_file": path})`` binds both sources to
    the same file while leaving the original definition unchanged.
    """
    directives = set(source_path_directives(definition))
    unknown = sorted(set(bindings) - directives)
    if unknown:
        raise KeyError(f"Unknown input directives: {', '.join(unknown)}")

    missing = sorted(directives - set(bindings))
    if missing:
        raise KeyError(f"Missing input directives: {', '.join(missing)}")

    values = {name: str(pathlib.Path(value)) for name, value in bindings.items()}
    sources = dict(definition.sources)
    for name, source in sources.items():
        source_path = getattr(source, "path", None)
        if source_path and any(field in directives for _, field, _, _ in string.Formatter().parse(source_path) if field):
            sources[name] = source.model_copy(update={"path": source_path.format_map(values)})
    return definition.model_copy(update={"sources": sources})
