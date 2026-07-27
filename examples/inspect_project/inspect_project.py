import pathlib

from project_generation import process_project_definition

EXAMPLE_DIRECTORY = pathlib.Path(__file__).resolve().parent
project = process_project_definition(EXAMPLE_DIRECTORY / "generation.json")
print(f"Project: {project.name}")
print(f"Pins: {len(project.pins)}")
print(f"Groups: {len(project.groups)}")
print(f"Device states: {len(project.device_states)}")
print(f"Test plans: {len(project.test_plans)}")
for plan in project.test_plans:
    print(f"- {plan.name}: {len(plan.test_groups)} test group(s)")
