import os
import pathlib

from project_generation import generate_project

EXAMPLE_DIRECTORY = pathlib.Path(__file__).resolve().parent
OUTPUT_DIRECTORY = pathlib.Path(os.environ.get("PROJECT_GENERATION_OUTPUT_DIRECTORY", "generated"))

project_path = generate_project(
    EXAMPLE_DIRECTORY / "generation.json",
    OUTPUT_DIRECTORY / "explicit-test-plan-project",
)
print(f"Created {project_path}")
