# Diagnostics and Validation

[Documentation home](../README.md) · [Getting started](getting-started.md)

Validation occurs at more than one stage because some errors can only be identified after source data and generated objects are resolved.

## Definition parsing

Loading a definition validates its typed structure:

```python
from project_generation import load_project_definition

definition = load_project_definition("generation.yaml")
```

Parsing catches malformed JSON or YAML, missing required fields, invalid field types, and unsupported structured values represented in the
model.

## Definition validation

Run semantic checks that are available before full processing:

```python
from project_generation import load_project_definition, validate_project_definition
from project_generation.application.workflows import raise_for_diagnostics

definition = load_project_definition("generation.yaml")
raise_for_diagnostics(validate_project_definition(definition))
```

## Processing validation

Full processing additionally validates relationships that depend on loaded source records and generated objects. Examples include:

- missing source files or invalid selected records;
- mappings that do not produce required normalized fields;
- explicit groups that reference unknown pins;
- rules that reference missing group parameters;
- unknown device states or power resources;
- insufficient available power resources;
- invalid ganging-policy or allocation-strategy names;
- circular device-state inheritance;
- unknown, self-referential, or circular power timing dependencies; and
- generated plans that cannot resolve their selected groups or stress values.

## Structured errors

Processing failures expose `ProjectGenerationError`:

```python
from project_generation import ProjectGenerationError, process_project_definition

try:
    project = process_project_definition("generation.yaml")
except ProjectGenerationError as error:
    print(error.code)
    print(error.location)
    print(error.owner)
    print(error.context)
    print(error.format_diagnostic())
```

The fields are intended to answer:

- **code**: what category of failure occurred;
- **location**: where in the definition or processing context it occurred;
- **owner**: which source, rule, state, plan, or object owns the failing value; and
- **context**: additional structured values relevant to the failure.

The normal exception message remains available for compatibility with existing callers.

## Recommended troubleshooting order

1. Confirm the intended definition and customer input file were used.
2. Validate the JSON or YAML syntax.
3. Check the reported location and owner.
4. Inspect the source record before changing generation rules.
5. Confirm named mappings cover the actual customer values.
6. Confirm group fields required by device-state or test-plan rules are present.
7. Check reserved, stress, and already assigned power resources.
8. Re-run generation after correcting the definition or source data.

## Common failures

### Source path not found

Resolve relative paths against the directory containing the definition. For batch workflows, replace input tokens before processing, as the
REALIS example does.

### Unknown mapped value

Add an explicit customer-to-normalized mapping only after confirming the meaning of the new source value. Do not map unknown values based
only on spelling similarity.

### Insufficient power resources

Review the generated groups requiring physical bias, explicit assignments, reserved resources, resources with the `STRESS` role, and the
selected ganging policy. Floating and ground assignments do not consume normal bias resources.

### Circular timing dependency

Inspect `timing.power_on.after` or `timing.power_off.after`. Every dependency graph must be acyclic, and every referenced domain must exist
in the resolved state.

### Unexpected number of plans

Calculate the expected expansion from selected partitions and dimensions. Then inspect exclusions and ordered overrides, which may remove or
change individual generated groups and plans.

## Capturing a customer issue

A useful issue report should include:

- package version or commit;
- the generation definition;
- a sanitized source record that reproduces the problem;
- the complete formatted diagnostic;
- the expected pins, groups, states, or plans.

Keep customer source data out of public issue trackers unless it has been explicitly sanitized and approved for that use.
