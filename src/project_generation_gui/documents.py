from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class TextDocument:
    path: Path
    text: str
    saved_text: str

    @classmethod
    def load(cls, path: str | Path) -> "TextDocument":
        resolved = Path(path).resolve()
        text = resolved.read_text(encoding="utf-8")
        return cls(path=resolved, text=text, saved_text=text)

    @property
    def dirty(self) -> bool:
        return self.text != self.saved_text

    def save(self) -> None:
        self.path.write_text(self.text, encoding="utf-8")
        self.saved_text = self.text

    def reload(self) -> None:
        text = self.path.read_text(encoding="utf-8")
        self.text = text
        self.saved_text = text


class DocumentManager:
    def __init__(self) -> None:
        self._documents: dict[Path, TextDocument] = {}

    def open(self, path: str | Path) -> TextDocument:
        resolved = Path(path).resolve()
        document = self._documents.get(resolved)
        if document is None:
            document = TextDocument.load(resolved)
            self._documents[resolved] = document
        return document

    def get(self, path: str | Path) -> TextDocument | None:
        return self._documents.get(Path(path).resolve())

    def documents(self) -> tuple[TextDocument, ...]:
        return tuple(self._documents.values())

    def save_all(self) -> None:
        for document in self._documents.values():
            if document.dirty:
                document.save()
