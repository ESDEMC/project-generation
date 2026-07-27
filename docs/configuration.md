# Configuration Guide

A generation definition describes where project data comes from and how that data is transformed into pins, groups, device states, and
test plans. JSON and YAML definitions use the same fields.

This guide introduces the major sections. The complete field behavior is defined in the
[format specification](project-generation-spec.md), and the generated JSON Schema is available at
[`project-generation.schema.json`](../project-generation.schema.json).

## Top-level structure

A typical rule-based definition contains these sections:

```yaml
schema_version: "1.0"
project: {}
mappings: {}
formatters: {}
sources: {}
dut: {}
groups: {}
power_resources: {}
device_states: {}
test_plan_generation: {}
```

Definitions may also contain explicit `test_plans` when plans should be listed directly rather than generated from rules.

## Schema version

`schema_version` identifies the version of the declarative format:

```yaml
schema_version: "1.0"
```

Keep this value explicit in customer definitions so future migrations can identify the expected structure.

## Project data

`project` supplies the generated project name and metadata. It can contain literal values or reference a normalized source record,
depending on the definition.

Literal example:

```yaml
project:
  name: Example Project
  metadata:
    customer: Example Customer
```

Source-backed example from the REALIS definition:

```yaml
project:
  source: realis_project
```

## Sources

Sources define how external records are loaded. Supported source forms are:

- `inline` for records embedded in the definition;
- `json` for JSON documents;
- `csv` for tabular text data; and
- `excel` when the optional Excel dependency is installed.

A JSON pin source can select records and map source fields into the normalized pin shape:

```yaml
sources:
  realis_pins:
    type: json
    path: "{input_file}"
    select: $.EsdPins[*]
    mapping:
      designator: Number
      name: Name
      parameters.pin_type:
        from: PinType
        mapping: realis_pin_type
      parameters.v_max: VoltageLevelMax
      parameters.v_min: VoltageLevelMin
```

The special `{input_file}` value is an example convention implemented by `examples/realis/generate_projects.py`. The core processor does
not replace it automatically; the example script substitutes the current input path before processing.

## Named mappings

Named mappings translate customer values into normalized values:

```yaml
mappings:
  realis_pin_type:
    I: INPUT
    Input: INPUT
    O: OUTPUT
    Output: OUTPUT
    IO: IO
    Supply: POWER
    Ground: GROUND
    not connected: NC
```

Use mappings at the source boundary. Internal rules can then operate on a consistent vocabulary even when customer exports use multiple
labels for the same concept.

## Formatters

Formatters convert resolved values into deterministic name fragments. The REALIS example uses a decimal token to create names such as
`In5V5`:

```yaml
formatters:
  voltage_token:
    type: decimal_token
    separator: V
    decimal_places: 1
```

Formatters are typically referenced by generated group or plan name fields.

## DUT and pins

The `dut` section identifies the DUT and the source used to create its pins:

```yaml
dut:
  name: REALIS DUT
  pins:
    source: realis_pins
```

Pins are normalized into designator, name, optional description, parameters, and a deterministic ID.

## Groups

Groups can be declared explicitly or generated from pin records.

Explicit groups are best when the exact membership is already known:

```yaml
groups:
  explicit:
    - name: GND
      group_type: GROUND
      pins: ["3"]
```

Generated groups are useful when pins should be partitioned by normalized fields:

```yaml
groups:
  generation:
    - id: groups_by_type_and_vmax
      group_by:
        - parameters.pin_type
        - parameters.v_max
      set:
        group_type:
          from: partition.parameters.pin_type
```

A generation rule can derive group fields from partition values, aggregate member values, and render a deterministic group name.

## Power resources

Power resources describe logical resources available during device-state allocation:

```yaml
power_resources:
  DC1:
    role: STRESS
  DC2:
    role: BIAS
  DC3:
    role: BIAS
```

Resources with the `STRESS` role and explicitly reserved resources are excluded from automatic bias assignment.

## Device states

Device states define how groups are biased for a test condition. They can use explicit power domains, rules, or inheritance.

Rule-based example:

```yaml
device_states:
  logic_low:
    allocation:
      mode: hybrid
      strategy: voltage_first
      reserve: [DC1]
      ganging_policy: same_voltage
    rules:
      - when:
          group.group_type: GROUND
        set:
          assignment: GROUND
          bias:
            mode: GROUND
      - when:
          group.group_type:
            in: [OUTPUT, NC]
        set:
          assignment: FLOATING
          bias:
            mode: FLOATING
```

Allocation modes are:

- `direct`: every required assignment must be explicit;
- `automatic`: assignments are selected from available resources; and
- `hybrid`: explicit assignments are preserved and remaining groups are allocated automatically.

The current ganging policies are `none` and `same_voltage`. `same_voltage` only reuses an assignment when the complete resolved bias
objects are equal.

## Test-plan generation

A test-plan generation rule selects groups, partitions them, expands dimensions, applies a template, and then applies ordered overrides.

```yaml
test_plan_generation:
  rules:
    - id: signal_tests
      groups:
        select:
          where:
            group_type:
              in: [INPUT, OUTPUT, IO]
        partition:
          mode: each
      dimensions:
        - name: logic_level
          values:
            - value: LOW
              set:
                device_state: logic_low
            - value: HIGH
              set:
                device_state: logic_high
      template:
        test_type: SIGNAL
        name:
          template: LU_{group.name}_{logic_level}
```

Dimension values can also set nested fields such as stress parameters. Overrides can target an entire plan or individual generated
groups.

## Stress parameters

Stress values can be scalar or expanded into a series. Common forms include:

```yaml
stress_parameters:
  peak: 5.5
```

```yaml
stress_parameters:
  peak:
    values: [5.5, 6.0, 6.5]
```

```yaml
stress_parameters:
  peak:
    from: group.v_max
    multiply_by: [1.0, 1.5]
```

The processor resolves these forms into concrete ordered stress points on each generated test group.

## Choosing explicit or generated configuration

Use explicit definitions when customer data already contains final project structure or when a small project requires exceptional control.
Use generated rules when the same policy applies across many devices or groups. Hybrid definitions are supported: explicit assignments,
groups, or plans can coexist with generated content where the model allows it.
