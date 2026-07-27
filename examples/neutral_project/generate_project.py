import os
import pathlib

from project_generation import process_project_definition, write_generated_project

EXAMPLE_DIRECTORY = pathlib.Path(__file__).resolve().parent
OUTPUT = pathlib.Path(os.environ.get("PROJECT_GENERATION_OUTPUT_DIRECTORY", "generated"))
output = OUTPUT / "minimal-explicit.generated.json"
project = process_project_definition(EXAMPLE_DIRECTORY / "generation.json")
write_generated_project(project, output)
print(f"Created {output}")
