"""Show how one stress rule can generate a voltage series and then change selected tests.

Relevant generation.json:

    {
      "stress_parameters.stress_voltage": {
        "from": "group.v_max",
        "add": [0.0, 0.5, 1.0, 1.5]
      }
    }

That creates a series from each group's voltage:

    IN_A positive   -> 5.0, 5.5, 6.0, 6.5 V
    OUT_A positive  -> 3.3, 3.8, 4.3, 4.8 V

Overrides change only the matching tests:

    Negative tests         -> hold time = 0.075 s
    Negative OUTPUT tests  -> compliance = 0.025 A

The normal settings remain unchanged for every other generated test.
"""


import pathlib

from project_generation import process_project_definition

EXAMPLE_DIRECTORY = pathlib.Path(__file__).resolve().parent
project = process_project_definition(EXAMPLE_DIRECTORY / "generation.json")

for plan in project.test_plans:
    for test_group in plan.test_groups:
        points = [point.values for point in test_group.stress_points]
        print(f"{plan.name} / {test_group.group_name}: {points}")
