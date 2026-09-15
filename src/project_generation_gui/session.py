import json
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from project_generation.definition.models import ProjectGenerationDefinition
from project_generation.definition.validation import validate_project_definition
from project_generation.diagnostics import ProjectGenerationError
from project_generation.generation.processor import ProjectGenerationProcessor
from project_generation.generation.snapshot import GenerationSnapshot

from .documents import DocumentManager, TextDocument


@dataclass(frozen=True, slots=True)
class SessionDiagnostic:
    severity: str
    code: str
    message: str
    location: str = ""


class ProjectSession:
    """Owns editor state and regenerates from in-memory document contents."""

    def __init__(self) -> None:
        self.documents = DocumentManager()
        self.definition_document: TextDocument | None = None
        self.definition: ProjectGenerationDefinition | None = None
        self.snapshot: GenerationSnapshot | None = None
        self.diagnostics: tuple[SessionDiagnostic, ...] = ()

    def open_definition(self, path: str | Path) -> None:
        self.definition_document = self.documents.open(path)
        self.regenerate()

    def update_document(self, path: str | Path, text: str) -> None:
        document = self.documents.get(path)
        if document is None:
            document = self.documents.open(path)
        document.text = text

    def save(self, path: str | Path) -> None:
        document = self.documents.get(path)
        if document is not None:
            document.save()

    def save_all(self) -> None:
        self.documents.save_all()

    def regenerate(self) -> None:
        document = self.definition_document
        if document is None:
            return

        try:
            definition = self._parse_definition(document)
        except (ValueError, yaml.YAMLError, json.JSONDecodeError, ValidationError) as error:
            self.diagnostics = (self._exception_diagnostic(error),)
            return

        definition_diagnostics = validate_project_definition(definition)
        diagnostics = tuple(
            SessionDiagnostic(
                severity=item.severity.value,
                code=item.code,
                message=item.message,
                location=item.location or "",
            )
            for item in definition_diagnostics
        )
        if any(item.severity.lower() == "error" for item in diagnostics):
            self.definition = definition
            self.diagnostics = diagnostics
            self._open_referenced_documents(definition)
            return

        self.definition = definition
        self._open_referenced_documents(definition)
        try:
            snapshot = self._generate_from_working_copy(definition)
        except Exception as error:  # surfaced as a diagnostic; GUI must survive generation failures
            self.diagnostics = diagnostics + (self._exception_diagnostic(error),)
            return

        self.snapshot = snapshot
        self.diagnostics = diagnostics

    def referenced_documents(self) -> tuple[TextDocument, ...]:
        if self.definition_document is None:
            return ()
        return tuple(doc for doc in self.documents.documents() if doc.path != self.definition_document.path)

    def _parse_definition(self, document: TextDocument) -> ProjectGenerationDefinition:
        suffix = document.path.suffix.lower()
        if suffix == ".json":
            definition = ProjectGenerationDefinition.model_validate_json(document.text)
        elif suffix in {".yaml", ".yml"}:
            data = yaml.safe_load(document.text)
            if data is None:
                data = {}
            if not isinstance(data, dict):
                raise ValueError("Generation definition must contain a top-level object")
            definition = ProjectGenerationDefinition.model_validate(data)
        else:
            raise ValueError(f"Unsupported generation definition format {suffix!r}")
        definition._definition_path = document.path
        return definition

    def _open_referenced_documents(self, definition: ProjectGenerationDefinition) -> None:
        base = self.definition_document.path.parent
        for source in definition.sources.values():
            source_path = getattr(source, "path", None)
            if source_path and "{" not in source_path:
                path = Path(source_path)
                if not path.is_absolute():
                    path = base / path
                if path.exists() and path.is_file():
                    self.documents.open(path)
        if definition.hardware is not None and "{" not in definition.hardware.source:
            path = Path(definition.hardware.source)
            if not path.is_absolute():
                path = base / path
            if path.exists() and path.is_file():
                self.documents.open(path)

    def _generate_from_working_copy(self, definition: ProjectGenerationDefinition) -> GenerationSnapshot:
        original_base = self.definition_document.path.parent
        with tempfile.TemporaryDirectory(prefix="project-generation-gui-") as temp_name:
            workspace = Path(temp_name)
            path_map: dict[Path, Path] = {}
            for index, document in enumerate(self.documents.documents()):
                try:
                    relative = document.path.relative_to(original_base)
                except ValueError:
                    relative = Path("_external") / str(index) / document.path.name
                target = workspace / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(document.text, encoding="utf-8")
                path_map[document.path] = target

            effective = self._redirect_external_paths(definition, original_base, workspace, path_map)
            definition_target = path_map[self.definition_document.path]
            effective._definition_path = definition_target
            return ProjectGenerationProcessor().process_with_snapshot(effective)

    @staticmethod
    def _redirect_external_paths(
        definition: ProjectGenerationDefinition,
        original_base: Path,
        workspace: Path,
        path_map: dict[Path, Path],
    ) -> ProjectGenerationDefinition:
        sources: dict[str, Any] = {}
        for name, source in definition.sources.items():
            source_path = getattr(source, "path", None)
            if not source_path or "{" in source_path:
                sources[name] = source
                continue
            original = Path(source_path)
            if not original.is_absolute():
                original = (original_base / original).resolve()
            target = path_map.get(original)
            if target is None:
                sources[name] = source
                continue
            sources[name] = source.model_copy(update={"path": str(target.relative_to(workspace))})

        hardware = definition.hardware
        if hardware is not None and "{" not in hardware.source:
            original = Path(hardware.source)
            if not original.is_absolute():
                original = (original_base / original).resolve()
            target = path_map.get(original)
            if target is not None:
                hardware = hardware.model_copy(update={"source": str(target.relative_to(workspace))})

        return definition.model_copy(update={"sources": sources, "hardware": hardware})

    @staticmethod
    def _exception_diagnostic(error: Exception) -> SessionDiagnostic:
        if isinstance(error, ValidationError):
            first = error.errors()[0]
            location = ".".join(str(part) for part in first.get("loc", ()))
            return SessionDiagnostic("error", "VALIDATION_ERROR", first.get("msg", str(error)), location)
        if isinstance(error, ProjectGenerationError):
            return SessionDiagnostic("error", error.code, str(error), error.location or "")
        return SessionDiagnostic("error", type(error).__name__, str(error))
