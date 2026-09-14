"""Show how group bias specs become concrete power domains for each device state.

Groups carry their baseline bias requirements. Device-state rules only modify
``bias_spec``; ganging decides which compatible groups may share a domain; the
allocator then chooses a DC resource for each domain.

Generated behavior:

    Domain contents      logic_low      logic_high
    -------------------  -------------  ----------------
    SU5V0                5.0 V / 200 mA 5.0 V / 200 mA
    SU3V3                3.3 V / 200 mA 3.3 V / 200 mA
    IN5V0                GND            5.0 V / 20 mA
    GND                  GND            GND

DC1 stays reserved for stress while the generator chooses DC2-DC4 for bias.
"""

import pathlib

from project_generation import process_project_definition

EXAMPLE_DIRECTORY = pathlib.Path(__file__).resolve().parent
project = process_project_definition(EXAMPLE_DIRECTORY / "generation.json")

for state in project.device_states:
    print(f"Device state: {state.name}")
    for domain in state.power_domains:
        groups = ", ".join(domain.group_names)
        print(f"  {domain.name}: [{groups}] -> {domain.assignment}, bias={domain.bias}")
