import os
import pathlib

from project_generation import generate_project

EXAMPLE_DIRECTORY = pathlib.Path(__file__).resolve().parent
OUTPUT = pathlib.Path(os.environ.get("PROJECT_GENERATION_OUTPUT_DIRECTORY", "generated")) / "latchup-projects"
DEFINITIONS = (
    EXAMPLE_DIRECTORY / "minimal-generation.json",
    EXAMPLE_DIRECTORY / "customer-generation.json",
)

for definition_path in DEFINITIONS:
    project_path = generate_project(definition_path, OUTPUT)
    print(f"Created {project_path}")
