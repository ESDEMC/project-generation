import os
import pathlib

from project_generation import generate_project, process_project_definition, write_generated_project

EXAMPLE_DIRECTORY = pathlib.Path(__file__).resolve().parent
OUTPUT = pathlib.Path(os.environ.get("PROJECT_GENERATION_OUTPUT_DIRECTORY", "generated")) / "customer-project"
DEFINITION = EXAMPLE_DIRECTORY / "generation.json"

project_path = generate_project(DEFINITION, OUTPUT / "latchup")
neutral_project = process_project_definition(DEFINITION)
neutral_path = OUTPUT / "customer-project.generated.json"
write_generated_project(neutral_project, neutral_path)

print(f"Created latch-up project: {project_path}")
print(f"Created optional neutral inspection file: {neutral_path}")
