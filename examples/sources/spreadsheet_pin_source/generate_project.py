"""Generate a project using DUT pins loaded from an Excel workbook.

The spreadsheet path in generation.yaml is relative to generation.yaml itself,
not to the directory where this script is launched.

Relevant generation.yaml:

    sources:
      customer_pins:
        type: excel
        path: ./data/customer-device.xlsx
        sheet: Pins
        mapping:
          designator: pin_number
          name: signal_name
          parameters.pin_type: latch_up_type

The Pins worksheet contains one pin per row. The source mapping converts the
spreadsheet column names into the project-generation pin model.
"""

import os
import pathlib

from project_generation import generate_project

EXAMPLE_DIRECTORY = pathlib.Path(__file__).resolve().parent
OUTPUT_DIRECTORY = pathlib.Path(os.environ.get("PROJECT_GENERATION_OUTPUT_DIRECTORY", "generated"))

project_path = generate_project(EXAMPLE_DIRECTORY / "generation.yaml", OUTPUT_DIRECTORY / "spreadsheet-pin-source")
print(f"Created {project_path}")
