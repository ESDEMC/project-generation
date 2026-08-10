"""Check a generation definition before creating a project.

This loads the same small explicit project used by generate_project.py and reports anything that is invalid.

Successful output:

    Definition is valid

Use this while editing a generation definition to catch problems before generating the project package.
"""


import pathlib

from project_generation import load_project_definition, raise_for_diagnostics, validate_project_definition

EXAMPLE_DIRECTORY = pathlib.Path(__file__).resolve().parent
definition = load_project_definition(EXAMPLE_DIRECTORY / "generation.json")
diagnostics = validate_project_definition(definition)
for diagnostic in diagnostics:
    print(diagnostic.format())
raise_for_diagnostics(diagnostics)
print("Definition is valid")
