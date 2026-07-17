import json
import pathlib
import typing

import yaml

DocumentT = typing.TypeVar("DocumentT", bound=typing.Any)


class JsonDocumentCodec(typing.Generic[DocumentT]):
    def __init__(self, document_type: type[DocumentT], *, indent: int = 2):
        self._document_type = document_type
        self._indent = indent

    def read(self, path: pathlib.Path | str) -> DocumentT:
        return self._document_type.from_json(pathlib.Path(path).read_text(encoding="utf-8"))

    def write(self, document: DocumentT, path: pathlib.Path | str) -> pathlib.Path:
        output_path = pathlib.Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(json.dumps(json.loads(document.to_json()), indent=self._indent) + "\n")
        return output_path
