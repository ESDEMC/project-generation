import argparse
import os
import pathlib

from project_generation import (
    load_project_definition,
    raise_for_diagnostics,
    replace_source_paths,
    validate_project_definition,
    generate_project,
)

EXAMPLE_DIRECTORY = pathlib.Path(__file__).resolve().parent
DEFAULT_DEFINITION_PATH = EXAMPLE_DIRECTORY / "generation.yaml"
DEFAULT_INPUT_DIRECTORY = EXAMPLE_DIRECTORY / "input"
DEFAULT_OUTPUT_DIRECTORY = pathlib.Path(
    os.environ.get("PROJECT_GENERATION_OUTPUT_DIRECTORY", EXAMPLE_DIRECTORY / "generated_projects")
)
REALIS_SOURCE_NAMES = ("realis_project", "realis_pins")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate latch-up project packages from REALIS exports using one shared definition."
    )
    parser.add_argument("inputs", nargs="*", type=pathlib.Path, help="REALIS JSON files; defaults to input/*.json")
    parser.add_argument("--definition", type=pathlib.Path, default=DEFAULT_DEFINITION_PATH)
    parser.add_argument("--output-directory", type=pathlib.Path, default=DEFAULT_OUTPUT_DIRECTORY)
    args = parser.parse_args()

    input_paths = args.inputs or sorted(DEFAULT_INPUT_DIRECTORY.glob("*.json"))
    if not input_paths:
        parser.error("No REALIS JSON input files were provided or found")

    for input_path in input_paths:
        project_path = generate_realis_project(args.definition, input_path, args.output_directory)
        print(f"Created {project_path}")


def generate_realis_project(definition_path: pathlib.Path, input_path: pathlib.Path, output_root: pathlib.Path) -> pathlib.Path:
    definition_path = definition_path.resolve()
    input_path = input_path.resolve()

    definition = load_project_definition(definition_path)
    definition = replace_source_paths(definition, {name: input_path for name in REALIS_SOURCE_NAMES})
    raise_for_diagnostics(validate_project_definition(definition))

    return generate_project(
        definition,
        output_root,
        base_directory=definition_path.parent,
        project_metadata={"source_file": input_path.name},
    )


if __name__ == "__main__":
    main()
