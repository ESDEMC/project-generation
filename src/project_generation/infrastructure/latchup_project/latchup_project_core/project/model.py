import pathlib
import typing
from dataclasses import dataclass, field

from mashumaro.mixins.json import DataClassJSONMixin


@dataclass(kw_only=True, frozen=True)
class ArtifactReference:
    path: pathlib.Path
    metadata: dict[str, typing.Any] = field(default_factory=dict)


@dataclass(kw_only=True)
class LatchUpProject(DataClassJSONMixin):
    output_directory: pathlib.Path = pathlib.Path("Output")
    test_directory: pathlib.Path = pathlib.Path("Testing")
    dut_path: pathlib.Path | None = None
    leakage_path: pathlib.Path | None = None
    test_plans: list[pathlib.Path] = field(default_factory=list)
    leakage_test_plans: list[pathlib.Path] = field(default_factory=list)
    project_data: dict[str, typing.Any] = field(default_factory=dict)
    artifacts: dict[str, list[ArtifactReference]] = field(default_factory=dict)
