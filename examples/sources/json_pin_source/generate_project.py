"""Generate a project using DUT pins loaded from a separate JSON file.

Relevant generation.json:

    {
      "sources": {
        "customer_pins": {
          "type": "json",
          "path": "./data/customer-device.json",
          "select": "$.pins[*]",
          "mapping": {
            "designator": "pin_number",
            "name": "signal_name",
            "parameters.pin_type": "latch_up_type"
          }
        }
      }
    }

A source record such as:

    {"pin_number": "2", "signal_name": "IN_A", "latch_up_type": "INPUT"}

becomes:

    2 -> IN_A (INPUT)

Use this when DUT information already exists in another data file.
"""


import os
import pathlib

from project_generation import generate_project

EXAMPLE_DIRECTORY = pathlib.Path(__file__).resolve().parent
OUTPUT_DIRECTORY = pathlib.Path(os.environ.get("PROJECT_GENERATION_OUTPUT_DIRECTORY", "generated"))

project_path = generate_project(EXAMPLE_DIRECTORY / "generation.json", OUTPUT_DIRECTORY / "json-pin-source")
print(f"Created {project_path}")
