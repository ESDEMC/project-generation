"""Generate a project using DUT pins loaded from an Excel workbook.

The spreadsheet path in generation.yaml is relative to generation.yaml itself,
not to the directory where this script is launched.

Relevant generation.yaml:

    sources:
      customer_project:
        type: excel
        path: ./data/customer-device.xlsx
        sheet: Project
        mapping:
          name: project_name
          metadata.product_basic_type: product_basic_type

      customer_pins:
        type: excel
        path: ./data/customer-device.xlsx
        sheet: Pins
        mapping:
          designator: pin_number
          name: signal_name
          parameters.pin_type: latch_up_type

    project:
      source: customer_project

    dut:
      name:
        template: '{project.metadata.product_basic_type}-{project.metadata.sales_code}'
      pins:
        source: customer_pins

The Project worksheet supplies project data and metadata. The DUT name template
combines product_basic_type and sales_code from that parsed metadata. The Pins
worksheet contains one pin per row. Both source paths are resolved relative to
generation.yaml.
"""

import os
import pathlib

from project_generation import generate_project

EXAMPLE_DIRECTORY = pathlib.Path(__file__).resolve().parent
OUTPUT_DIRECTORY = pathlib.Path(os.environ.get("PROJECT_GENERATION_OUTPUT_DIRECTORY", "generated"))

project_path = generate_project(EXAMPLE_DIRECTORY / "generation.yaml", OUTPUT_DIRECTORY / "spreadsheet-pin-source")
print(f"Created {project_path}")
