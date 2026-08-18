"""Show how pin groups can be created automatically from pin information.

Relevant generation.json:

    {
      "groups": {
        "generation": [{
          "group_by": ["parameters.pin_type", "parameters.v_max", "parameters.v_min"]
        }]
      }
    }

Pins with the same type and voltage are placed in the same generated group:

    SU5V5  -> VDD
    IN5V5  -> IN_A, IN_B
    OUT3V3 -> OUT_A
    GND    -> GND (defined explicitly)

Use this when many groups follow the same grouping rule and should not be written by hand.
"""


import pathlib

from project_generation import process_project_definition

EXAMPLE_DIRECTORY = pathlib.Path(__file__).resolve().parent
project = process_project_definition(EXAMPLE_DIRECTORY / "generation.json")

pin_name_by_id = {pin.id: pin.name for pin in project.pins}
for group in project.groups:
    pins = ", ".join(pin_name_by_id[pin_id] for pin_id in group.pin_ids)
    print(f"{group.name} -> {pins}")
