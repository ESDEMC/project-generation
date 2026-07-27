# Getting Started

This guide generates a concrete latch-up project package from a project definition. Latch-up is the default project format; the neutral
generated model is an optional inspection and extension boundary.

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
    "examples/latchup_project/generation.json",
    "generated",
)
print(project_path)
```

The generated package contains the `.Prj`, `.LuDut`, and `.LuTstPlan` files consumed by the latch-up application.

## Write an inspection file

To inspect the format-independent intermediate model, write the neutral result to JSON explicitly:

```python
from project_generation import process_project_definition, write_generated_project

project = process_project_definition("examples/neutral_project/generation.json")
write_generated_project(project, "generated-project.json")
```

Review this file to confirm:

- all expected pins were loaded;
- pin designators and names were mapped correctly;
- groups contain the correct pin IDs;
- device states have the expected assignments and bias values;
- power sequences are ordered correctly; and
- the expected plans and stress points were generated.

## Validate without processing

Definition validation can be run separately:

```python
from project_generation import load_project_definition, raise_for_diagnostics, validate_project_definition

definition = load_project_definition("examples/neutral_project/generation.json")
raise_for_diagnostics(validate_project_definition(definition))
```

Definition validation checks the parsed configuration. Full processing performs additional checks that depend on resolved pins, groups,
device states, resources, and generated plans.

## Use YAML

JSON and YAML definitions use the same model. YAML is often easier to maintain for larger rule-based definitions:

```yaml
schema_version: "1.0"
project:
  name: Example Project

dut:
  name: Example DUT
  pins:
    source:
      type: inline
      records:
        - designator: "1"
          name: VDD
          parameters:
            pin_type: POWER
            v_max: 5.5
```

## Next steps

Continue with the [configuration guide](configuration.md), then use the [processing model](processing-model.md) to understand how the
sections are resolved. For customer exports, see [REALIS integration](realis-integration.md).

## Runnable Python examples

Each runnable example is stored in a self-contained directory under `examples/`. The script, generation definition, and any required input data are kept together.

Representative examples include:

- `examples/validate_definition/validate_definition.py` validates its adjacent `generation.json`.
- `examples/neutral_project/generate_project.py` writes a neutral generated-project JSON file.
- `examples/inspect_project/inspect_project.py` demonstrates programmatic inspection.
- `examples/realis/override_source_path.py` replaces named source paths before processing.
- `examples/latchup_project/generate_project.py` writes a complete latch-up project package.

Run an example from the repository root:

```bash
python examples/neutral_project/generate_project.py
```
