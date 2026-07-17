# Project Generation

A standalone processor for declarative `generation.json` files.

The core package owns parsing, normalization, semantic validation, dynamic dimension expansion, test-group partitioning, ordered overrides, and stress-series expansion. It deliberately does not depend on concrete latch-up project classes or file formats.

## Public API

```python
from project_generation import load_project_definition, validate_project_definition

definition = load_project_definition("generation.json")
diagnostics = validate_project_definition(definition)
```

Rule processing operates on neutral group records:

```python
from project_generation import GroupRecord, expand_rule

candidates = expand_rule(rule, groups=[GroupRecord(name="IN5V5", group_type="INPUT", parameters={"v_max": 5.5})])
```

Concrete `.LuDut`, `.LuTstPlan`, or project generation belongs in an external adapter consuming the eventual neutral generated-project model.

## Development

```bash
python -m pip install -e ".[dev]"
pytest
```

## Processing a definition

```python
from project_generation import process_project_definition

generated = process_project_definition("generation.json")

for pin in generated.pins:
    print(pin.designator, pin.name, pin.id)

for group in generated.groups:
    print(group.name, group.group_type, group.pin_ids)
```

The processor supports inline, JSON, CSV, and optional Excel pin sources, target-to-source record mappings, deterministic
pin and group IDs, explicit and generated groups, resolved device states, and generated test plans. Device states include
inheritance, explicit power domains, per-group rules, deterministic power assignments, and deterministic plan references.
Automatic and hybrid allocation preserve explicit assignments while excluding reserved and stress resources. Named power-domain
timing is compiled into deterministic `power_on_sequence` and `power_off_sequence` steps with resolved `after` dependencies and delays. Concrete latch-up
project files remain outside this package and can consume the neutral `GeneratedProject` model through adapters.

## Current processing coverage

`ProjectGenerationProcessor` now produces neutral pins, groups, and test plans. Test-plan processing includes explicit plans, group partitioning, dynamic dimensions, ordered plan and group overrides, exclusions, name-template rendering, and concrete per-group stress points.

Tests resolve example files relative to the test module rather than the process working directory, and the suite is verified both from the repository root and from an unrelated working directory.

## Project tracking

- `CHANGELOG.md` records implemented behavior and notable changes.
- `ROADMAP.md` tracks feature slices without committing the package to speculative infrastructure.

## Power ganging

Automatic and hybrid allocation support `ganging_policy: "none"` and `ganging_policy: "same_voltage"`. The same-voltage policy only reuses a physical resource when the complete resolved bias objects are equal.


## Power sequencing

Each generated device state includes a deterministic sequence compiled from its named power domains:

```python
for step in state.power_on_sequence:
    print(step.index, step.domain_name, step.after, step.delay)

for step in state.power_off_sequence:
    print(step.index, step.domain_name, step.after, step.delay)
```

Power-on domains without dependencies preserve declaration order. When no explicit power-off timing is provided, power-off defaults
to the reverse of the resolved power-on sequence. `timing.power_off.after` can define an explicit shutdown dependency graph. Missing
references, self-references, and circular dependencies fail during project processing.

## Generated-project inspection

The neutral generated model can be inspected or handed to another process as JSON:

```python
from project_generation import process_project_definition, write_generated_project

project = process_project_definition("generation.json")
write_generated_project(project, "generated-project.json")
```

## Structured diagnostics

Processing failures remain ordinary `ValueError` exceptions, but now expose a structured diagnostic payload:

```python
try:
    project = process_project_definition("generation.json")
except ProjectGenerationError as error:
    print(error.code)
    print(error.location)
    print(error.owner)
    print(error.context)
    print(error.format_diagnostic())
```

The plain exception message is preserved for compatibility with existing callers and tests.


## Latch-up project-core adapter

When `latchup-core` and `latchup-project-core` are installed, the neutral model can be converted to the real application domain objects:

```python
from project_generation import adapt_to_latchup_project, process_project_definition

generated = process_project_definition("generation.json")
artifacts = adapt_to_latchup_project(generated)

print(artifacts.dut)
print(artifacts.test_plans)
```

The imports are lazy, so these packages are not mandatory for parsing or neutral generation. The first adapter maps DUT pins and groups,
device states, power assignments, power-on/off timing, plan dimensions, and plan group selection. Provisional stress points are retained in
`LatchUpTestPlan.metadata["generated_stress_points"]`; executable `StressPlan` conversion is intentionally deferred until the real stress
calculation is implemented.


The latch-up adapter creates a real `StressPlan` on each generated `LatchUpTestPlan`. Direct stress points map `stress_voltage`/`peak`, `compliance`, and `hold_time` into `LatchUpPulseParameters`; optional pulse and measurement timing fields are also supported.

## REALIS project-generation example

Run `python examples/realis/generate_projects.py` to generate latch-up project packages from the JSON files in
`examples/realis/input`. An alternate input and output directory can be supplied as positional arguments.
