import pathlib
from collections.abc import Mapping

from project_generation.diagnostics import GenerationDiagnostics, ProjectGenerationError
from project_generation.models import ProjectGenerationDefinition


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
    """Return a copy of a definition with selected file-source paths replaced."""
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
