import pathlib
import typing

from dataclasses import dataclass, field, asdict
from dataclasses_json import DataClassJsonMixin


def relative_to(path, other):
    return pathlib.Path(path).resolve().relative_to(pathlib.Path(other).resolve())


def find_paths(data) -> typing.Generator[tuple[dict | list, str | int, pathlib.Path], None, None]:
    for key, value in data.items():
        if isinstance(value, dict):
            yield from find_paths(value)
        elif isinstance(value, (str, pathlib.Path)):
            yield data, key, pathlib.Path(value)
        elif isinstance(value, list):
            for i, item in enumerate(value):
                if isinstance(item, pathlib.Path):
                    yield value, i, item


@dataclass
class Project(DataClassJsonMixin):
    project_file_path: pathlib.Path | None
    output_directory: pathlib.Path | None = None
    test_directory: pathlib.Path | None = None
    leakage_path: pathlib.Path | None = None
    dut_path: pathlib.Path | None = None
    device_state_path: pathlib.Path | None = None
    pin_map: pathlib.Path | None = None
    preconditioning_path: pathlib.Path | None = None
    test_plans: list[pathlib.Path] = field(default_factory=list)
    project_data: dict = field(default_factory=dict)

    def save(self, path=None):
        prj_pat = path or self.project_file_path
        data = asdict(self)
        data.pop("project_file_path")

        for d, key, path_ in find_paths(data):
            d[key] = relative_to(path_, prj_pat.parent)

        with open(path, "w") as f:
            f.write(self.to_json(indent=4))

    @classmethod
    def load(cls, path):
        with open(path, "r") as f:
            text = f.read()
            return cls.from_json(text)


