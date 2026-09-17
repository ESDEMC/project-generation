import json
from dataclasses import asdict, dataclass, replace
from hashlib import sha256
from pathlib import Path

from qtpy.QtCore import QByteArray, QSettings


@dataclass(frozen=True, slots=True)
class SessionState:
    definition_path: str
    input_bindings: tuple[tuple[str, str], ...] = ()
    open_documents: tuple[str, ...] = ()
    generated_views: tuple[str, ...] = ()
    dirty_documents: tuple[tuple[str, str], ...] = ()
    current_document: str | None = None
    export_directory: str | None = None

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> "SessionState":
        return cls(
            definition_path=str(value["definition_path"]),
            input_bindings=tuple(tuple(item) for item in value.get("input_bindings", ())),
            open_documents=tuple(str(item) for item in value.get("open_documents", ())),
            generated_views=tuple(str(item) for item in value.get("generated_views", ())),
            dirty_documents=tuple(tuple(item) for item in value.get("dirty_documents", ())),
            current_document=str(value["current_document"]) if value.get("current_document") else None,
            export_directory=str(value["export_directory"]) if value.get("export_directory") else None,
        )


class SessionStore:
    MAX_RECENT = 12

    def __init__(self, settings: QSettings) -> None:
        self._settings = settings

    def recent(self) -> tuple[SessionState, ...]:
        raw = self._settings.value("sessions/recent", "[]")
        try:
            values = json.loads(str(raw))
        except (TypeError, ValueError, json.JSONDecodeError):
            return ()
        states = []
        for value in values:
            try:
                state = SessionState.from_dict(value)
            except (KeyError, TypeError, ValueError):
                continue
            states.append(state)
        return tuple(states)

    def state_for(self, definition_path: str | Path) -> SessionState | None:
        target = str(Path(definition_path).resolve())
        return next((state for state in self.recent() if state.definition_path == target), None)

    def last(self) -> SessionState | None:
        path = self._settings.value("sessions/last")
        if not path:
            return None
        return self.state_for(str(path))

    def save(self, state: SessionState, central_state: QByteArray | None = None) -> None:
        target = str(Path(state.definition_path).resolve())
        normalized = replace(state, definition_path=target)
        recent = [item for item in self.recent() if item.definition_path != target]
        recent.insert(0, normalized)
        recent = recent[: self.MAX_RECENT]
        self._settings.setValue("sessions/recent", json.dumps([asdict(item) for item in recent]))
        self._settings.setValue("sessions/last", target)
        if central_state is not None:
            self._settings.setValue(self._central_state_key(target), central_state)
        self._settings.sync()

    def central_state(self, definition_path: str | Path) -> QByteArray | None:
        value = self._settings.value(self._central_state_key(str(Path(definition_path).resolve())))
        return value if isinstance(value, QByteArray) else None

    def clear_recent(self) -> None:
        self._settings.remove("sessions/recent")
        self._settings.remove("sessions/last")
        self._settings.sync()

    @staticmethod
    def _central_state_key(definition_path: str) -> str:
        digest = sha256(definition_path.encode("utf-8")).hexdigest()
        return f"sessions/central_state/{digest}"
