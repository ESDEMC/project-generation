import pathlib
import typing

from .model import ArtifactReference, LatchUpProject
from ..shared import JsonDocumentCodec


class ProjectBuilder:
    def __init__(self) -> None:
        self._project = LatchUpProject()

    def set_project_data(self, **project_data: typing.Any) -> typing.Self:
        self._project.project_data.update(project_data)
        return self

    def build(self) -> LatchUpProject:
        return self._project


class ProjectPackageBuilder:
    def __init__(self, project: LatchUpProject | None = None) -> None:
        self.project = project or LatchUpProject()
        self._staged: list[tuple[str, typing.Any, pathlib.Path, typing.Any]] = []

    def stage(self, role: str, value: typing.Any, *, relative_path: str, writer: typing.Any) -> typing.Self:
        path = pathlib.Path(relative_path)
        self.project.artifacts.setdefault(role, []).append(ArtifactReference(path=path))
        self._staged.append((role, value, path, writer))
        if role == "dut":
            self.project.dut_path = path
        elif role == "leakage_config":
            self.project.leakage_path = path
        elif role == "latch_up_test_plan":
            self.project.test_plans.append(path)
        elif role == "leakage_test_plan":
            self.project.leakage_test_plans.append(path)
        return self

    def build(self, project_file: pathlib.Path | str) -> pathlib.Path:
        project_path = pathlib.Path(project_file)
        project_path.parent.mkdir(parents=True, exist_ok=True)
        for _role, value, relative_path, writer in self._staged:
            writer.write(value, project_path.parent / relative_path)
        (project_path.parent / self.project.output_directory).mkdir(exist_ok=True)
        (project_path.parent / self.project.test_directory).mkdir(exist_ok=True)
        JsonDocumentCodec(LatchUpProject).write(self.project, project_path)
        return project_path
