from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Iterable


class DiagnosticSeverity(StrEnum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass(frozen=True, kw_only=True)
class GenerationDiagnostic:
    severity: DiagnosticSeverity
    code: str
    message: str
    location: str | None = None
    context: dict[str, Any] = field(default_factory=dict)

    def format(self) -> str:
        location = f" at {self.location}" if self.location else ""
        return f"{self.severity.value.upper()} {self.code}{location}: {self.message}"


class GenerationDiagnostics(list[GenerationDiagnostic]):
    def __init__(self, values: Iterable[GenerationDiagnostic] = ()) -> None:
        super().__init__(values)

    @property
    def has_errors(self) -> bool:
        return any(item.severity == DiagnosticSeverity.ERROR for item in self)


class ProjectGenerationError(ValueError):
    """Processing failure with a stable diagnostic payload."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "generation_error",
        location: str | None = None,
        owner: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        self.diagnostic = GenerationDiagnostic(
            severity=DiagnosticSeverity.ERROR,
            code=code,
            message=message,
            location=location,
            context={
                **({"owner": owner} if owner is not None else {}),
                **(context or {}),
            },
        )
        self.code = code
        self.location = location
        self.owner = owner
        self.context = self.diagnostic.context
        super().__init__(message)

    def format_diagnostic(self) -> str:
        return self.diagnostic.format()
