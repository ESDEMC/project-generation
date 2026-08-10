"""Show how one test rule can expand into many test plans.

Relevant generation.json:

    {
      "dimensions": [
        {"name": "logic_level", "values": ["LOW", "HIGH"]},
        {"name": "polarity", "values": ["POSITIVE", "NEGATIVE"]}
      ]
    }

Each selected group receives every combination:

    LOW  + POSITIVE
    LOW  + NEGATIVE
    HIGH + POSITIVE
    HIGH + NEGATIVE

Three groups x four combinations produces 12 test plans.
"""


import pathlib

from project_generation import process_project_definition

EXAMPLE_DIRECTORY = pathlib.Path(__file__).resolve().parent
project = process_project_definition(EXAMPLE_DIRECTORY / "generation.json")

for plan in project.test_plans:
    groups = ", ".join(group.group_name for group in plan.test_groups)
    print(f"{plan.name}: groups=[{groups}], dimensions={plan.dimensions}")
