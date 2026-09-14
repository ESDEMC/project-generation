"""Use hardware.yaml as the physical source for bias and stress resolution.

The generation definition does not declare DC resources itself. The hardware
file supplies connected matrix assignments, connection modes, DC envelopes,
and Source Switch PULSE envelopes.

The POWER groups define only the required voltage. During device-state
resolution those specs are completed with the default 200 mA compliance before
hardware compatibility is checked. DC1 remains reserved for stress.
"""

import pathlib

from project_generation import process_project_definition

EXAMPLE_DIRECTORY = pathlib.Path(__file__).resolve().parent
project = process_project_definition(EXAMPLE_DIRECTORY / "generation.yaml")

for state in project.device_states:
    print(f"Device state: {state.name}")
    for domain in state.power_domains:
        groups = ", ".join(domain.group_names)
        print(f"  {domain.name}: [{groups}] -> {domain.assignment}, bias={domain.bias}")

for plan in project.test_plans:
    if plan.stress_supply is not None:
        print(f"Stress supply: {plan.name} -> {plan.stress_supply.resource} [{plan.stress_supply.strategy}]")
