"""Generate one complete Latch-Up project from a hand-written definition.

Relevant generation.json:

    {
      "groups": {
        "explicit": [
          {"name": "SU5V5", "group_type": "POWER", "pins": ["1"]},
          {"name": "IN5V5", "group_type": "INPUT", "pins": ["2"]},
          {"name": "GND", "group_type": "GROUND", "pins": ["3"]}
        ]
      },
      "test_plans": [
        {"name": "IN5V5_HIGH_POSITIVE", "test_type": "SIGNAL", "device_state": "logic_high"}
      ]
    }

The definition produces one small project:

    Pins       -> VDD, IN_A, GND
    Groups     -> SU5V5, IN5V5, GND
    DUT state  -> IN5V5 and SU5V5 powered at 5.5 V
    Test       -> IN5V5_HIGH_POSITIVE
    Stress     -> 5.5 V, 6.0 V, 6.5 V

Run this first to see the simplest end-to-end workflow from definition to generated project package.
"""


import os
import pathlib

from project_generation import generate_project

EXAMPLE_DIRECTORY = pathlib.Path(__file__).resolve().parent
OUTPUT_DIRECTORY = pathlib.Path(os.environ.get("PROJECT_GENERATION_OUTPUT_DIRECTORY", "generated"))

project_path = generate_project(EXAMPLE_DIRECTORY / "generation.json", OUTPUT_DIRECTORY / "explicit-project")
print(f"Created {project_path}")
