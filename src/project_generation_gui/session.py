import json
import shutil
import tempfile
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from project_generation.application.workflows import (
    bind_input_files,
    required_source_path_directives,
    source_path_directives,
)
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
        self.input_bindings: dict[str, Path] = {}

    def open_definition(self, path: str | Path) -> None:
        self.documents = DocumentManager()
        self.input_bindings.clear()
        self.definition_document = self.documents.open(path)
        self.definition = None
        self.snapshot = None
        self.diagnostics = ()
        self.regenerate(report_missing_inputs=False)

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

    def export_project_directory(self, output_directory: str | Path) -> Path:
        self.regenerate()
        if self.definition is None or self.snapshot is None or any(
            item.severity.lower() == "error" for item in self.diagnostics
        ):
            raise ProjectGenerationError(
                "Cannot export while the current working copy has errors",
                code="export.validation_failed",
            )

        from project_generation.infrastructure.latchup_project.writer import safe_file_name

        return Path(output_directory).resolve() / safe_file_name(self.snapshot.generated_project.name)

    def export_project(self, output_directory: str | Path, *, overwrite: bool = False) -> Path:
        self.regenerate()
        if self.definition is None or any(item.severity.lower() == "error" for item in self.diagnostics):
            raise ProjectGenerationError(
                "Cannot export while the current working copy has errors",
                code="export.validation_failed",
            )

        try:
            from project_generation.infrastructure.latchup_project.writer import LatchUpProjectWriter, safe_file_name

            generated = self._process_working_copy_strict(self.definition)
            project_directory = Path(output_directory).resolve() / safe_file_name(generated.name)
            if project_directory.exists():
                if not overwrite:
                    raise FileExistsError(project_directory)
                if project_directory.is_dir():
                    shutil.rmtree(project_directory)
                else:
                    project_directory.unlink()
            return LatchUpProjectWriter().write(generated, output_directory)
        except Exception as error:
            if not isinstance(error, ProjectGenerationError):
                traceback.print_exception(error)
            diagnostic = self._exception_diagnostic(error)
            self.diagnostics = self.diagnostics + (diagnostic,)
            raise

    def clear_diagnostics(self) -> None:
        """Clear the currently displayed diagnostics until the next regeneration pass."""
        self.diagnostics = ()

    def input_directives(self) -> tuple[str, ...]:
        if self.definition is None:
            return ()
        return source_path_directives(self.definition)

    def set_input_file(self, directive: str, path: str | Path) -> None:
        directive = directive.strip()
        if not directive:
            raise ValueError("Input directive cannot be empty")
        valid_directives = set(self.input_directives())
        if directive not in valid_directives:
            raise KeyError(f'Unknown input directive "{directive}"')
        resolved = Path(path).resolve()
        if not resolved.is_file():
            raise FileNotFoundError(resolved)
        self.input_bindings[directive] = resolved
        self.documents.open(resolved)
        self.regenerate(report_missing_inputs=False)

    def clear_input_file(self, directive: str) -> None:
        self.input_bindings.pop(directive, None)
        self.regenerate(report_missing_inputs=False)

    def input_documents(self) -> tuple[tuple[str, TextDocument], ...]:
        result: list[tuple[str, TextDocument]] = []
        for directive in self.input_directives():
            path = self.input_bindings.get(directive)
            if path is None:
                continue
            document = self.documents.get(path)
            if document is not None:
                result.append((directive, document))
        return tuple(result)

    def regenerate(self, *, report_missing_inputs: bool = True) -> None:
        document = self.definition_document
        if document is None:
            return

        try:
            payload = self._parse_document_syntax(document)
        except (ValueError, yaml.YAMLError, json.JSONDecodeError) as error:
            self.diagnostics = (self._syntax_diagnostic(error, document.path),)
            return

        try:
            definition = self._validate_definition(payload, document)
        except ValidationError as error:
            self.diagnostics = (self._schema_diagnostic(error),)
            return

        self.definition = definition
        self._open_referenced_documents(definition)

        syntax_diagnostics = tuple(
            diagnostic
            for source_document in self.active_documents()
            if source_document.path != document.path
            for diagnostic in self._document_syntax_diagnostics(source_document)
        )
        if syntax_diagnostics:
            self.diagnostics = syntax_diagnostics
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
            self.diagnostics = diagnostics
            return

        missing_inputs = tuple(
            name for name in required_source_path_directives(definition) if name not in self.input_bindings
        )
        if missing_inputs:
            self.snapshot = None
            if report_missing_inputs:
                missing_diagnostics = tuple(
                    SessionDiagnostic(
                        "error",
                        "INPUT_FILE_NOT_SET",
                        f'Input file for directive "{name}" has not been selected',
                        f"inputs.{name}",
                    )
                    for name in missing_inputs
                )
                self.diagnostics = diagnostics + missing_diagnostics
            else:
                self.diagnostics = diagnostics
            return

        try:
            snapshot = self._generate_from_working_copy(definition)
        except Exception as error:
            if not isinstance(error, ProjectGenerationError):
                traceback.print_exception(error)
            self.diagnostics = diagnostics + (self._exception_diagnostic(error),)
            return

        self.snapshot = snapshot
        generation_diagnostics = tuple(
            SessionDiagnostic(
                severity=item.severity.value,
                code=item.code,
                message=item.message,
                location=item.location or "",
            )
            for item in snapshot.diagnostics
        )
        self.diagnostics = diagnostics + generation_diagnostics

    def referenced_documents(self) -> tuple[TextDocument, ...]:
        if self.definition is None or self.definition_document is None:
            return ()
        paths = self._referenced_paths(self.definition)
        return tuple(document for path in paths if (document := self.documents.get(path)) is not None)

    def active_documents(self) -> tuple[TextDocument, ...]:
        """Documents that currently participate in this project generation."""
        if self.definition_document is None:
            return ()
        active: list[TextDocument] = [self.definition_document]
        seen = {self.definition_document.path}
        for _directive, document in self.input_documents():
            if document.path not in seen:
                active.append(document)
                seen.add(document.path)
        for document in self.referenced_documents():
            if document.path not in seen:
                active.append(document)
                seen.add(document.path)
        return tuple(active)

    def _referenced_paths(self, definition: ProjectGenerationDefinition) -> tuple[Path, ...]:
        base = self.definition_document.path.parent
        paths: list[Path] = []
        for source in definition.sources.values():
            source_path = getattr(source, "path", None)
            if not source_path or "{" in source_path:
                continue
            path = Path(source_path)
            if not path.is_absolute():
                path = base / path
            resolved = path.resolve()
            if resolved.is_file() and resolved not in paths:
                paths.append(resolved)
        if definition.hardware is not None and "{" not in definition.hardware.source:
            path = Path(definition.hardware.source)
            if not path.is_absolute():
                path = base / path
            resolved = path.resolve()
            if resolved.is_file() and resolved not in paths:
                paths.append(resolved)
        return tuple(paths)

    @staticmethod
    def _parse_document_syntax(document: TextDocument) -> Any:
        suffix = document.path.suffix.lower()
        if suffix == ".json":
            return json.loads(document.text)
        if suffix in {".yaml", ".yml"}:
            return yaml.safe_load(document.text)
        raise ValueError(f"Unsupported generation definition format {suffix!r}")

    @staticmethod
    def _validate_definition(payload: Any, document: TextDocument) -> ProjectGenerationDefinition:
        if payload is None:
            payload = {}
        definition = ProjectGenerationDefinition.model_validate(payload)
        definition._definition_path = document.path
        return definition

    def _document_syntax_diagnostics(self, document: TextDocument) -> tuple[SessionDiagnostic, ...]:
        if document.path.suffix.lower() not in {".json", ".yaml", ".yml"}:
            return ()
        try:
            self._parse_document_syntax(document)
        except (yaml.YAMLError, json.JSONDecodeError) as error:
            return (self._syntax_diagnostic(error, document.path),)
        return ()

    def _open_referenced_documents(self, definition: ProjectGenerationDefinition) -> None:
        for path in self._referenced_paths(definition):
            self.documents.open(path)

    def _generate_from_working_copy(self, definition: ProjectGenerationDefinition) -> GenerationSnapshot:
        return self._run_in_working_copy(
            definition,
            lambda effective: ProjectGenerationProcessor().process_best_effort(effective),
        )

    def _process_working_copy_strict(self, definition: ProjectGenerationDefinition):
        return self._run_in_working_copy(
            definition,
            lambda effective: ProjectGenerationProcessor().process(effective),
        )

    def _run_in_working_copy(self, definition: ProjectGenerationDefinition, operation):
        original_base = self.definition_document.path.parent
        with tempfile.TemporaryDirectory(prefix="project-generation-gui-") as temp_name:
            workspace = Path(temp_name)
            path_map: dict[Path, Path] = {}
            for index, document in enumerate(self.active_documents()):
                try:
                    relative = document.path.relative_to(original_base)
                except ValueError:
                    relative = Path("_external") / str(index) / document.path.name
                target = workspace / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(document.text, encoding="utf-8")
                path_map[document.path] = target

            directives = set(source_path_directives(definition))
            effective_bindings = {
                name: path_map.get(path, path)
                for name, path in self.input_bindings.items()
                if name in directives
            }
            effective = bind_input_files(definition, effective_bindings)
            effective = self._redirect_external_paths(effective, original_base, workspace, path_map)
            effective._definition_path = path_map[self.definition_document.path]
            return operation(effective)

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
            if not source_path:
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
    def _syntax_diagnostic(error: Exception, path: Path) -> SessionDiagnostic:
        line = column = None
        if isinstance(error, json.JSONDecodeError):
            line, column = error.lineno, error.colno
            message = error.msg
        elif isinstance(error, yaml.MarkedYAMLError) and error.problem_mark is not None:
            line = error.problem_mark.line + 1
            column = error.problem_mark.column + 1
            message = error.problem or str(error)
        else:
            message = str(error)

        location = path.name
        if line is not None and column is not None:
            location = f"{location}:{line}:{column}"
        return SessionDiagnostic("error", "SYNTAX_ERROR", message, location)

    @staticmethod
    def _schema_diagnostic(error: ValidationError) -> SessionDiagnostic:
        first = error.errors()[0]
        location = ".".join(str(part) for part in first.get("loc", ()))
        return SessionDiagnostic("error", "SCHEMA_VALIDATION_ERROR", first.get("msg", str(error)), location)

    @staticmethod
    def _exception_diagnostic(error: Exception) -> SessionDiagnostic:
        if isinstance(error, ValidationError):
            return ProjectSession._schema_diagnostic(error)
        if isinstance(error, ProjectGenerationError):
            return SessionDiagnostic("error", error.code, str(error), error.location or "")
        return SessionDiagnostic("error", type(error).__name__, str(error))
