# Getting Started

[Documentation home](../README.md) · [Configuration](configuration.md) · [Examples](examples.md) · [Diagnostics](diagnostics.md)

This guide shows the normal end-user workflow: define a project, validate the definition, and generate a Latch-Up project package.

## Requirements

- Python 3.11 or newer
- A JSON or YAML generation definition
- Any external source files referenced by that definition

Install the package from the repository root:

```bash
python -m pip install -e .
```

For development and test tools:

```bash
python -m pip install -e ".[dev]"
```

## Generate the included example

The default public workflow writes a latch-up project package:

```python
from project_generation import generate_project

project_path = generate_project(
    "examples/basics/explicit_project/generation.json",
    "generated",
)
print(project_path)
```

The generated package contains the `.Prj`, `.LuDut`, and `.LuTstPlan` files consumed by the latch-up application.

## Validate without processing

Definition validation can be run separately:

```python
from project_generation import load_project_definition, raise_for_diagnostics, validate_project_definition

definition = load_project_definition("examples/basics/explicit_project/generation.json")
raise_for_diagnostics(validate_project_definition(definition))
```

Definition validation checks the parsed configuration. Full processing performs additional checks that depend on resolved pins, groups,
device states, resources, and generated plans.

## Write the generation definition

The focused examples use JSON. A small inline definition starts like this:

```json
{
  "schema_version": "1.0",
  "project": {"name": "Example Project"},
  "dut": {
    "name": "Example DUT",
    "pins": {
      "source": {
        "type": "inline",
        "records": [
          {"designator": "1", "name": "VDD", "parameters": {"pin_type": "POWER", "v_max": 5.5}}
        ]
      }
    }
  }
}
```

If the pins already live in a customer JSON export, replace the inline records with a named source:

```json
{
  "sources": {
    "customer_pins": {
      "type": "json",
      "path": "./data/customer-device.json",
      "select": "$.pins[*]",
      "mapping": {
        "designator": "pin_number",
        "name": "signal_name"
      }
    }
  },
  "dut": {
    "name": "Example DUT",
    "pins": {"source": "customer_pins"}
  }
}
```

YAML is also supported and uses the same fields. The REALIS real-world example uses YAML because that is the maintained definition for that workflow.

## Next steps

Continue with the [configuration guide](configuration.md), then use the [processing model](processing-model.md) to understand how the
sections are resolved. For customer exports, see [REALIS real-world example](../real-world/realis.md).

## Runnable Python examples

Each runnable example is stored in a self-contained directory under `examples/`. The script, generation definition, and any required input data are kept together.

Representative examples include:

- [`examples/basics/explicit_project/validate_definition.py`](../../examples/basics/explicit_project/validate_definition.py) validates its adjacent [`generation.json`](../../examples/basics/explicit_project/generation.json).
- [`examples/real_world/realis/generate_projects.py`](../../examples/real_world/realis/generate_projects.py) uses the adjacent [`generation.yaml`](../../examples/real_world/realis/generation.yaml) for each REALIS input.
- [`examples/basics/explicit_project/generate_project.py`](../../examples/basics/explicit_project/generate_project.py) writes a complete Latch-Up project package.

Run an example from the repository root:

```bash
python examples/basics/explicit_project/generate_project.py
```
