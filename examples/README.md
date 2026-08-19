# Examples

[Documentation home](../docs/README.md) · [Detailed example guide](../docs/user/examples.md)

Examples are organized by the end-user task they demonstrate. Each folder contains the generation file and the Python script that uses it.
There are no per-example README files; open the demo script first for a short explanation, then the generation file for the configuration.

```text
examples/
├── basics/
│   └── explicit_project/                    Write a complete project directly
├── sources/
│   ├── json_pin_source/                     Load and map pins from external JSON
│   ├── spreadsheet_pin_source/              Load and map pins from an Excel workbook
│   └── hardware_config/                     Load physical power resources from hardware.yaml
├── customizing_generation/
│   ├── group_generation/                    Generate groups from pin properties
│   ├── device_states_and_power_allocation/  Generate DUT states and assign DC resources
│   ├── test_plan_dimensions/                Expand one rule into combinations of test plans
│   └── stress_series_and_overrides/         Generate stress series and change selected cases
└── real_world/
    └── realis/                              Complete REALIS batch-generation workflow
```

## Recommended order

1. [`basics/explicit_project/generate_project.py`](basics/explicit_project/generate_project.py)
2. [`sources/json_pin_source/generate_project.py`](sources/json_pin_source/generate_project.py)
3. [`sources/spreadsheet_pin_source/generate_project.py`](sources/spreadsheet_pin_source/generate_project.py)
4. [`sources/hardware_config/demo.py`](sources/hardware_config/demo.py)
5. [`customizing_generation/group_generation/demo.py`](customizing_generation/group_generation/demo.py)
6. [`customizing_generation/device_states_and_power_allocation/demo.py`](customizing_generation/device_states_and_power_allocation/demo.py)
7. [`customizing_generation/test_plan_dimensions/demo.py`](customizing_generation/test_plan_dimensions/demo.py)
8. [`customizing_generation/stress_series_and_overrides/demo.py`](customizing_generation/stress_series_and_overrides/demo.py)
9. [`real_world/realis/generate_projects.py`](real_world/realis/generate_projects.py)

Run scripts from the repository root. For example:

```bash
python examples/customizing_generation/group_generation/demo.py
```

Use [`docs/user/examples.md`](../docs/user/examples.md) when you want the JSON snippets and explanation for each example.
