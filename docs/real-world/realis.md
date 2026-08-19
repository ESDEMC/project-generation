# REALIS real-world example

[Documentation home](../README.md) · [Configuration](../user/configuration.md)

The REALIS example demonstrates the intended customer workflow: one shared generation definition is applied to multiple exported device
records, producing a separate latch-up project package for each input.

## Files

```text
examples/real_world/realis/
├── README.md                Example-specific guidance
├── generation.yaml          Shared source mappings and generation rules
├── generate_projects.py     Batch generation and packaging script
└── input/                   REALIS JSON exports
```

## Run the example

Process every JSON file in the default input directory:

```bash
python examples/real_world/realis/generate_projects.py
```

Process selected files:

```bash
python examples/real_world/realis/generate_projects.py path/to/device-a.json path/to/device-b.json
```

Use another definition or output directory:

```bash
python examples/real_world/realis/generate_projects.py path/to/device.json \
    --definition path/to/generation.yaml \
    --output-directory path/to/generated-projects
```

## Input substitution

The shared definition declares source paths using `{input_file}`:

```yaml
sources:
  realis_project:
    type: json
    path: "{input_file}"
    select: $
  realis_pins:
    type: json
    path: "{input_file}"
    select: $.EsdPins[*]
```

`generate_projects.py` replaces this token with the current input file before calling the processor. This is script-level behavior, not an
implicit feature of `process_project_definition()`.

## Project metadata mapping

The `realis_project` source selects the root record and maps customer fields into the generated project:

```yaml
mapping:
  name: ProjectName
  metadata.test_id: TestId
  metadata.project_id: ProjectId
  metadata.lab_tracking_number: LabTrackingNo
  metadata.project_owner: ProjectOwner
  metadata.department: Department
  metadata.standard: ActualStandard
```

Additional mapped metadata is retained on the generated project and passed into the packaged project by the example script.

## Pin normalization

The `realis_pins` source selects `EsdPins` and maps each record:

```yaml
mapping:
  designator: Number
  name: Name
  parameters.pin_type:
    from: PinType
    mapping: realis_pin_type
  parameters.v_max: VoltageLevelMax
  parameters.v_min: VoltageLevelMin
```

The `realis_pin_type` mapping normalizes customer labels before the generation rules use them.

```text
I / Input      -> INPUT
O / Output     -> OUTPUT
Supply         -> POWER
Ground         -> GROUND
```

## Group generation

Pins are grouped by normalized pin type and maximum voltage. Group values are derived from the partition and its members, then group names
are rendered from a type prefix and formatted voltage token.

This produces stable names:

```text
5.5 V input   -> In5V5
28.0 V output -> O28V0
5.5 V supply  -> Su5V5
ground pins   -> GND
```

Always review generated membership when customer exports contain incomplete or inconsistent voltage data. Pins with different grouping
fields will intentionally be placed into different groups.

## Hardware configuration

The REALIS definition uses the shared hardware example as its physical power-resource source:

```yaml
hardware:
  source: ../../sources/hardware_config/hardware.yaml
```

The hardware file defines the connected matrix assignments, connection modes, and DC power envelopes. Device-state allocation therefore
uses only connected bias-capable resources that can realize the requested voltage. `DC1` is present in the hardware configuration as the
switch/stress connection and is not available for ordinary bias allocation.

## Device states

The example defines `logic_low` and `logic_high` states.

Both states:

- reserve `DC1` for stress;
- use hybrid, voltage-first allocation against `hardware.yaml`;
- permit exact same-bias ganging;
- ground ground groups; and
- leave output and NC groups floating.

For `logic_low`, input and IO groups are grounded while power groups are biased to their maximum voltage. For `logic_high`, input, IO, and
power groups are biased to their maximum voltage.

These are project-generation rules and must be reviewed against the customer's intended test behavior before delivery.

Some supplied REALIS exports intentionally exceed the connected hardware. In particular, a device state that needs more simultaneous
distinct bias voltages than the available bias channels is rejected instead of being assigned to a nonexistent DC resource. This is a
hardware-compatibility diagnostic, not a generation fallback.
When the batch example encounters one of these exports, it prints the complete hardware-resolution report, including every unresolved
group and the reason each candidate power resource was rejected, skips that file, and continues processing the remaining inputs.

## Generated test plans

The shared definition creates two plan families.

### Signal plans

Signal groups include `INPUT`, `OUTPUT`, and `IO`. Each group is expanded across `HIGH`/`LOW` logic and positive/negative polarity.
The semantic dimension values stay unchanged, but mappings shorten them in the generated name:

```yaml
mappings:
  logic_level_token:
    HIGH: H
    LOW: L
  polarity_token:
    POSITIVE: '+'
    NEGATIVE: '-'
```

The test-plan name uses those mapped fields:

```yaml
name:
  template: LU_{group}_{logic}{polarity}
  fields:
    group:
      source: group.name
    logic:
      source: logic_level
      mapping: logic_level_token
    polarity:
      source: polarity
      mapping: polarity_token
```

For one signal group, the generated order is:

```text
(HIGH, POSITIVE) -> LU_<group>_H+
(LOW,  POSITIVE) -> LU_<group>_L+
(HIGH, NEGATIVE) -> LU_<group>_H-
(LOW,  NEGATIVE) -> LU_<group>_L-
```

Plan and group overrides adjust selected hold-time and compliance values after the base template is applied.

### Supply plans

Supply tests have logic level but no polarity. The same logic mapping gives names such as:

```text
(HIGH) -> LU_<group>_H
(LOW)  -> LU_<group>_L
```

## Output package

For each input file, the example creates a sanitized project directory and stages:

- one `.LuDut` file;
- one `.LuTstPlan` file per generated plan; and
- one `.Prj` project manifest.

The exact package writing is implemented by the latch-up project-core builders used in `generate_projects.py`.

## Customer-data onboarding checklist

Before processing a new REALIS export variant:

1. compare its root fields and `EsdPins` records with the existing mapping;
2. identify every observed `PinType` value and update `realis_pin_type` when necessary;
3. confirm voltage fields use the expected units and null representation;
4. run generation into a clean output directory;
5. inspect the resulting project package in the target application;
6. compare generated pin and group counts with the source export;
7. review floating, grounded, and powered groups in each device state;
8. review the complete generated plan list and stress values; and
9. run the repository tests before packaging a delivery.

Do not silently add guessed mappings for unknown customer values. Unknown or inconsistent data should produce a documented mapping change
or a diagnostic that can be reviewed with the customer.

## Public API boundary

The REALIS example imports exclusively from `project_generation`. Its workflow is:

1. `load_project_definition()` loads the shared YAML definition.
2. `replace_source_paths()` binds the named `realis_project` and `realis_pins` sources to the current export.
3. `validate_project_definition()` and `raise_for_diagnostics()` stop generation when semantic errors exist.
4. `generate_project()` resolves the configured generation rules and writes the Latch-Up project package.

The example uses only the supported public API. Internal processing and package-writing details are intentionally hidden from the end-user workflow.
