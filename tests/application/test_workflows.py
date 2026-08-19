from tests.support.paths import EXPLICIT_PROJECT, REALIS, ROOT
import pathlib

import pytest

from project_generation import (
    load_project_definition,
    validate_project_definition,
)
from project_generation.application.workflows import raise_for_diagnostics, replace_source_paths
from project_generation.diagnostics import GenerationDiagnostic, GenerationDiagnostics, DiagnosticSeverity, ProjectGenerationError


def test_replace_source_paths_returns_updated_copy() -> None:
    definition = load_project_definition(REALIS / "generation.yaml")
    updated = replace_source_paths(
        definition,
        {"realis_project": "device.json", "realis_pins": "device.json"},
    )

    assert updated.sources["realis_project"].path == "device.json"
    assert updated.sources["realis_pins"].path == "device.json"
    assert definition.sources["realis_project"].path == "{input_file}"


def test_replace_source_paths_rejects_unknown_source() -> None:
    definition = load_project_definition(EXPLICIT_PROJECT)
    with pytest.raises(KeyError, match="Unknown source names"):
        replace_source_paths(definition, {"missing": "device.json"})


def test_raise_for_diagnostics_accepts_warnings() -> None:
    diagnostics = GenerationDiagnostics([
        GenerationDiagnostic(severity=DiagnosticSeverity.WARNING, code="EXAMPLE", message="Example warning")
    ])
    raise_for_diagnostics(diagnostics)


def test_raise_for_diagnostics_raises_for_errors() -> None:
    diagnostics = GenerationDiagnostics([
        GenerationDiagnostic(severity=DiagnosticSeverity.ERROR, code="EXAMPLE", message="Example error")
    ])
    with pytest.raises(ProjectGenerationError, match="definition is invalid"):
        raise_for_diagnostics(diagnostics)


def test_generate_project_uses_latchup_format_by_default(tmp_path: pathlib.Path) -> None:
    from project_generation import generate_project

    project_path = generate_project(EXPLICIT_PROJECT, tmp_path)

    assert project_path.suffix == ".Prj"
    assert project_path.is_file()
    assert list(project_path.parent.glob("*.LuDut"))
    assert list(project_path.parent.glob("Testing/*.LuTstPlan"))


def test_generate_project_accepts_custom_format(tmp_path: pathlib.Path) -> None:
    from collections.abc import Mapping
    from typing import Any

    from project_generation import (
        GeneratedProject,
        ProjectWriter,
        generate_project,
    )

    class TextProjectWriter(ProjectWriter):
        def write(
            self,
            project: GeneratedProject,
            output_directory: str | pathlib.Path,
            *,
            project_metadata: Mapping[str, Any] | None = None,
        ) -> pathlib.Path:
            output_path = pathlib.Path(output_directory) / "project.txt"
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(project.name, encoding="utf-8")
            return output_path

    project_path = generate_project(
        EXPLICIT_PROJECT,
        tmp_path,
        project_writer=TextProjectWriter(),
    )

    assert project_path.read_text(encoding="utf-8") == "Minimal Explicit Project"


def test_loaded_definition_uses_its_own_directory(tmp_path: pathlib.Path) -> None:
    from project_generation import generate_project

    definition = load_project_definition(EXPLICIT_PROJECT)
    project_path = generate_project(definition, tmp_path)

    assert project_path.is_file()
