import pathlib

from project_generation import load_project_definition, raise_for_diagnostics, validate_project_definition

EXAMPLE_DIRECTORY = pathlib.Path(__file__).resolve().parent
definition = load_project_definition(EXAMPLE_DIRECTORY / "generation.json")
diagnostics = validate_project_definition(definition)
for diagnostic in diagnostics:
    print(diagnostic.format())
raise_for_diagnostics(diagnostics)
print("Definition is valid")
