"""Use hardware.yaml as the physical source for bias and stress resolution.

The generation definition does not declare DC resources itself. The hardware file supplies connected matrix assignments, connection
modes, DC envelopes, and Source Switch PULSE envelopes.

Relevant generation.yaml:

    hardware:
      source: hardware.yaml

    device_states:
      powered:
        allocation:
          mode: hybrid
          strategy: voltage_first
          reserve: [DC1]

    test_plans:
    - name: LU_IN
      test_type: SIGNAL
      test_groups:
      - group: IN
        stress_points:
        - source_mode: voltage
          base: 5.0
          peak: 30.0
          compliance: 0.5
          pulse_width: 0.01

With the supplied hardware configuration, DC1 is a Source Switch. Its DC envelopes must support the 5 V pre/post bias and one of its
PULSE envelopes must support the 30 V, 0.5 A, 10 ms stress as a complete operating region. DC2 and DC3 remain normal bias resources.
"""

import pathlib

from project_generation import process_project_definition

EXAMPLE_DIRECTORY = pathlib.Path(__file__).resolve().parent
project = process_project_definition(EXAMPLE_DIRECTORY / "generation.yaml")

for state in project.device_states:
    print(f"Device state: {state.name}")
    for assignment in state.power_assignments:
        print(f"  {assignment.group_name}: {assignment.assignment}, bias={assignment.bias}")

for plan in project.test_plans:
    if plan.stress_supply is not None:
        print(f"Stress supply: {plan.name} -> {plan.stress_supply.resource} [{plan.stress_supply.strategy}]")
