"""Generate Latch-Up projects from REALIS export files.

Each REALIS JSON file is converted using one shared generation.yaml definition:

    REALIS data                         Used for
    ----------------------------------  ------------------------------------
    Project fields                      Project name and metadata
    EsdPins[*]                          DUT pins
    Pin type / voltage fields           Generated pin groups
    Pin groups and voltage information  DUT states and generated test plans
    Shared hardware.yaml                Available DC resources and limits

Command-line input files are processed when supplied. With no input arguments, every JSON file in input/ is processed.
This is the example closest to a real customer workflow.
"""


import argparse
import os
import pathlib

from project_generation import (
    load_project_definition,
    validate_project_definition,
    generate_project,
    PowerResourceResolutionError,
    StressSupplyResolutionError,
    ProjectGenerationError,
)
from project_generation.application.workflows import bind_input_files, raise_for_diagnostics

EXAMPLE_DIRECTORY = pathlib.Path(__file__).resolve().parent
DEFAULT_DEFINITION_PATH = EXAMPLE_DIRECTORY / "generation.yaml"
DEFAULT_INPUT_DIRECTORY = EXAMPLE_DIRECTORY / "input"
DEFAULT_ADAPTER_BOARD_PATH = EXAMPLE_DIRECTORY / "adapter-board.csv"
DEFAULT_OUTPUT_DIRECTORY = pathlib.Path(
    os.environ.get("PROJECT_GENERATION_OUTPUT_DIRECTORY", EXAMPLE_DIRECTORY / "generated")
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate latch-up project packages from REALIS exports using one shared definition."
    )
    parser.add_argument("inputs", nargs="*", type=pathlib.Path, help="REALIS JSON files; defaults to input/*.json")
    parser.add_argument("--definition", type=pathlib.Path, default=DEFAULT_DEFINITION_PATH)
    parser.add_argument("--output-directory", type=pathlib.Path, default=DEFAULT_OUTPUT_DIRECTORY)
    parser.add_argument("--adapter-board", type=pathlib.Path)
    args = parser.parse_args()

    input_paths = args.inputs or sorted(DEFAULT_INPUT_DIRECTORY.glob("*.json"))
    if not input_paths:
        parser.error("No REALIS JSON input files were provided or found")

    for input_path in input_paths:
        try:
            project_path = generate_realis_project(
                args.definition,
                input_path,
                args.output_directory,
                adapter_board_path=args.adapter_board,
            )
        except (PowerResourceResolutionError, StressSupplyResolutionError) as error:
            print(f"Skipped {input_path.name}")
            print(error.format_user_report())
            continue
        except ProjectGenerationError as error:
            print(f"Skipped {input_path.name}: {error.format_diagnostic()}")
            continue
        print(f"Created {project_path}")


def generate_realis_project(
    definition_path: pathlib.Path,
    input_path: pathlib.Path,
    output_root: pathlib.Path,
    *,
    adapter_board_path: pathlib.Path | None = None,
) -> pathlib.Path:
    definition_path = definition_path.resolve()
    input_path = input_path.resolve()

    definition = load_project_definition(definition_path)
    bindings = {"input_file": input_path}
    if adapter_board_path is not None:
        bindings["adapter_board"] = adapter_board_path.resolve()
    definition = bind_input_files(definition, bindings)
    raise_for_diagnostics(validate_project_definition(definition))

    return generate_project(
        definition,
        output_root,
        base_directory=definition_path.parent,
        project_metadata={"source_file": input_path.name},
    )


if __name__ == "__main__":
    main()
