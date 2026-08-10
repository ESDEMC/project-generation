import pathlib
import re
from collections.abc import Mapping
from typing import Any

from project_generation.infrastructure.latchup_project.latchup_adapter import adapt_to_latchup_project
from project_generation.infrastructure.latchup_project.latchup_project_core.project import ProjectBuilder, ProjectPackageBuilder
from project_generation.infrastructure.latchup_project.latchup_project_core.shared import JsonDocumentCodec
from project_generation.application.ports import ProjectWriter
from project_generation.generation.models import GeneratedProject


def safe_file_name(value: str) -> str:
    """Convert a generated name into a portable project artifact name."""
    normalized = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    return normalized.strip("._") or "project"


def write_latchup_project_package(
    generated: GeneratedProject,
    output_directory: str | pathlib.Path,
    *,
    project_metadata: Mapping[str, Any] | None = None,
) -> pathlib.Path:
    """Write a generated project as a latch-up project package.

    This is the public packaging boundary. Callers do not need to know about the
    embedded latch-up project-core builders or codecs.
    """
    artifacts = adapt_to_latchup_project(generated)
    package_name = safe_file_name(generated.name)
    root = pathlib.Path(output_directory).resolve() / package_name
    root.mkdir(parents=True, exist_ok=True)

    metadata = {**generated.metadata, **(project_metadata or {})}
    project = ProjectBuilder().set_project_data(**metadata).build()
    package = ProjectPackageBuilder(project)
    package.stage(
        "dut",
        artifacts.dut,
        relative_path=f"{package_name}.LuDut",
        writer=JsonDocumentCodec(type(artifacts.dut)),
    )
    for test_plan in artifacts.test_plans:
        package.stage(
            "latch_up_test_plan",
            test_plan,
            relative_path=f"Testing/{safe_file_name(test_plan.name)}.LuTstPlan",
            writer=JsonDocumentCodec(type(test_plan)),
        )
    return package.build(root / f"{package_name}.Prj")


class LatchUpProjectWriter(ProjectWriter):
    """Concrete format for the latch-up application's project package."""

    def write(
        self,
        project: GeneratedProject,
        output_directory: str | pathlib.Path,
        *,
        project_metadata: Mapping[str, Any] | None = None,
    ) -> pathlib.Path:
        return write_latchup_project_package(project, output_directory, project_metadata=project_metadata)
