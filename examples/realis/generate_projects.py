import argparse
import json
import pathlib
import re
from typing import Any

from project_generation.extensions.latchup_project.latchup_project_core.project import ProjectBuilder, ProjectPackageBuilder
from project_generation.extensions.latchup_project.latchup_project_core.shared import JsonDocumentCodec

from project_generation import ProjectGenerationProcessor, adapt_to_latchup_project, load_project_definition


EXAMPLE_DIRECTORY = pathlib.Path(__file__).resolve().parent
DEFAULT_DEFINITION_PATH = EXAMPLE_DIRECTORY / "generation.yaml"
DEFAULT_INPUT_DIRECTORY = EXAMPLE_DIRECTORY / "input"
DEFAULT_OUTPUT_DIRECTORY = EXAMPLE_DIRECTORY / "generated_projects"
REALIS_SOURCE_NAME = "realis_pins"
INPUT_PATH_TOKEN = "{input_file}"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate latch-up projects from REALIS exports using one shared generation definition."
    )
    parser.add_argument("inputs", nargs="*", type=pathlib.Path, help="REALIS JSON files; defaults to every JSON file in input")
    parser.add_argument("--definition", type=pathlib.Path, default=DEFAULT_DEFINITION_PATH)
    parser.add_argument("--output-directory", type=pathlib.Path, default=DEFAULT_OUTPUT_DIRECTORY)
    args = parser.parse_args()

    input_paths = args.inputs or sorted(DEFAULT_INPUT_DIRECTORY.glob("*.json"))
    if not input_paths:
        parser.error("No REALIS JSON input files were provided or found in the input directory")

    for input_path in input_paths:
        project_path = generate_project(args.definition, input_path, args.output_directory)
        print(f"Created {project_path}")


def generate_project(definition_path: pathlib.Path, input_path: pathlib.Path, output_root: pathlib.Path) -> pathlib.Path:
    definition_path = definition_path.resolve()
    input_path = input_path.resolve()
    source = json.loads(input_path.read_text(encoding="utf-8"))
    project_name, dut_name = names_from_realis(input_path, source)

    definition = load_project_definition(definition_path)
    realis_source = definition.sources[REALIS_SOURCE_NAME]
    if realis_source.path != INPUT_PATH_TOKEN:
        raise ValueError(
            f"{definition_path} must use {INPUT_PATH_TOKEN!r} as sources.{REALIS_SOURCE_NAME}.path, "
            f"not {realis_source.path!r}"
        )

    definition = definition.model_copy(
        update={
            "project": definition.project.model_copy(update={"name": project_name}),
            "dut": definition.dut.model_copy(update={"name": dut_name}) if definition.dut else None,
            "sources": {
                **definition.sources,
                REALIS_SOURCE_NAME: realis_source.model_copy(update={"path": str(input_path)}),
            },
        }
    )

    generated = ProjectGenerationProcessor().process(definition, base_directory=definition_path.parent)
    artifacts = adapt_to_latchup_project(generated)
    output_directory = output_root.resolve() / file_name(project_name)
    output_directory.mkdir(parents=True, exist_ok=True)

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
        "dut",
        artifacts.dut,
        relative_path=f"{file_name(project_name)}.LuDut",
        writer=JsonDocumentCodec(type(artifacts.dut)),
    )
    for test_plan in artifacts.test_plans:
        package.stage(
            "latch_up_test_plan",
            test_plan,
            relative_path=f"Testing/{file_name(test_plan.name)}.LuTstPlan",
            writer=JsonDocumentCodec(type(test_plan)),
        )

    return package.build(output_directory / f"{file_name(project_name)}.Prj")


def names_from_realis(input_path: pathlib.Path, source: dict[str, Any]) -> tuple[str, str]:
    file_identity = input_path.name.split(".", 1)[0]
    _, separator, dut_name = file_identity.partition("_")
    dut_name = dut_name if separator else file_identity
    project_name = f"{source.get('LabTrackingNo', file_identity)}_{dut_name}"
    return project_name, dut_name


def file_name(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    return normalized.strip("._") or "project"


if __name__ == "__main__":
    main()
