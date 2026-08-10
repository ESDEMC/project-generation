"""Show how the same DUT can be powered differently for different test conditions.

Relevant generation.json:

    {
      "device_states": {
        "logic_low": {
          "allocation": {"mode": "hybrid", "reserve": ["DC1"]},
          "rules": [{"when": {"group.group_type": "INPUT"}, "set": {"assignment": "GROUND"}}]
        },
        "logic_high": {
          "allocation": {"mode": "hybrid", "reserve": ["DC1"]}
        }
      }
    }

Generated behavior:

    Group   logic_low   logic_high
    ------  ----------  ----------
    SU5V0   5.0 V       5.0 V
    SU3V3   3.3 V       3.3 V
    IN5V0   GND         5.0 V
    GND     GND         GND

DC1 stays reserved for stress while the generator chooses DC2-DC4 for bias.
"""


import pathlib

from project_generation import process_project_definition

EXAMPLE_DIRECTORY = pathlib.Path(__file__).resolve().parent
project = process_project_definition(EXAMPLE_DIRECTORY / "generation.json")

for state in project.device_states:
    print(f"Device state: {state.name}")
    for assignment in state.power_assignments:
        print(f"  {assignment.group_name}: {assignment.assignment}, bias={assignment.bias}")
