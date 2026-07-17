import argparse
import json
import pathlib
import re
import shutil
from typing import Any

from project_generation.extensions.latchup_project.latchup_project_core.project import ProjectBuilder, ProjectPackageBuilder
from project_generation.extensions.latchup_project.latchup_project_core.shared import JsonDocumentCodec

from project_generation import adapt_to_latchup_project, process_project_definition


EXAMPLE_DIRECTORY = pathlib.Path(__file__).resolve().parent
DEFAULT_DEFINITION_DIRECTORY = EXAMPLE_DIRECTORY / "projects"
DEFAULT_OUTPUT_DIRECTORY = EXAMPLE_DIRECTORY / "generated_projects"
GENERATION_FILE_NAME = "generation.json"
REALIS_SOURCE_NAME = "realis_pins"


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate latch-up projects from concrete REALIS generation definitions.")
    parser.add_argument("definition_directory", nargs="?", type=pathlib.Path, default=DEFAULT_DEFINITION_DIRECTORY)
    parser.add_argument("output_directory", nargs="?", type=pathlib.Path, default=DEFAULT_OUTPUT_DIRECTORY)
    args = parser.parse_args()

    generation_paths = sorted(args.definition_directory.glob(f"*/{GENERATION_FILE_NAME}"))
    if not generation_paths:
        raise SystemExit(f"No {GENERATION_FILE_NAME} files found below {args.definition_directory}")

    for generation_path in generation_paths:
        output_directory = args.output_directory / generation_path.parent.name
        project_path = generate_project(generation_path, output_directory)
        print(f"Created {project_path}")


def generate_project(generation_path: pathlib.Path, output_directory: pathlib.Path) -> pathlib.Path:
    definition = json.loads(generation_path.read_text(encoding="utf-8"))
    input_path = resolve_realis_export_path(generation_path, definition)
    source = json.loads(input_path.read_text(encoding="utf-8"))

    generated = process_project_definition(generation_path)
    artifacts = adapt_to_latchup_project(generated)
    project_name = file_name(generated.name)

    if output_directory.exists():
        shutil.rmtree(output_directory)
    output_directory.mkdir(parents=True)

    project = ProjectBuilder().set_project_data(
        source="REALIS",
        source_file=input_path.name,
        test_id=source.get("TestId"),
        lab_tracking_number=source.get("LabTrackingNo"),
        standard=source.get("ActualStandard"),
        machine=source.get("Machine"),
        verifier_board=source.get("VerifierBoard"),
        remark=source.get("Remark", ""),
    ).build()

    package = ProjectPackageBuilder(project)
    package.stage(
        "dut", artifacts.dut, relative_path=f"{project_name}.LuDut", writer=JsonDocumentCodec(type(artifacts.dut))
    )
    for test_plan in artifacts.test_plans:
        package.stage(
            "latch_up_test_plan",
            test_plan,
            relative_path=f"Testing/{file_name(test_plan.name)}.LuTstPlan",
            writer=JsonDocumentCodec(type(test_plan)),
        )

    return package.build(output_directory / f"{project_name}.Prj")


def resolve_realis_export_path(generation_path: pathlib.Path, definition: dict[str, Any]) -> pathlib.Path:
    try:
        source_definition = definition["sources"][REALIS_SOURCE_NAME]
        source_path = source_definition["path"]
    except (KeyError, TypeError) as error:
        raise ValueError(f'{generation_path} must define sources.{REALIS_SOURCE_NAME}.path') from error

    input_path = (generation_path.parent / source_path).resolve()
    if not input_path.is_file():
        raise FileNotFoundError(f"REALIS export not found: {input_path}")
    return input_path


def file_name(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    return value.strip("._") or "project"


if __name__ == "__main__":
    main()
