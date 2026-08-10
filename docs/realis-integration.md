# REALIS Integration

The REALIS example demonstrates the intended customer workflow: one shared generation definition is applied to multiple exported device
records, producing a separate latch-up project package for each input.

## Files

```text
examples/realis/
├── generation.yaml          Shared source mappings and generation rules
├── generate_projects.py     Batch generation and packaging script
├── input/                   REALIS JSON exports
└── generated_projects/      Generated customer project packages
```

## Run the example

Process every JSON file in the default input directory:

```bash
python examples/realis/generate_projects.py
```

Process selected files:

```bash
python examples/realis/generate_projects.py path/to/device-a.json path/to/device-b.json
```

Use another definition or output directory:

```bash
python examples/realis/generate_projects.py path/to/device.json \
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

The `realis_pin_type` mapping normalizes customer labels such as `I`, `Input`, `O`, `Output`, `Supply`, and `Ground` into the group types used
by the generation rules.

## Group generation

Pins are grouped by normalized pin type and maximum voltage. Group values are derived from the partition and its members, then group names
are rendered from a type prefix and formatted voltage token.

This produces stable names such as:

- `In5V5` for a 5.5 V input group;
- `O28V0` for a 28.0 V output group;
- `Su5V5` for a 5.5 V supply group; and
- `GND` for ground pins.

Always review generated membership when customer exports contain incomplete or inconsistent voltage data. Pins with different grouping
fields will intentionally be placed into different groups.

## Device states

The example defines `logic_low` and `logic_high` states.

Both states:

- reserve `DC1` for stress;
- use hybrid, voltage-first allocation;
- permit exact same-bias ganging;
- ground ground groups; and
- leave output and NC groups floating.

For `logic_low`, input and IO groups are grounded while power groups are biased to their maximum voltage. For `logic_high`, input, IO, and
power groups are biased to their maximum voltage.

These are project-generation rules and must be reviewed against the customer's intended test behavior before delivery.

## Generated test plans

The shared definition creates two plan families.

### Signal plans

Signal groups include `INPUT`, `OUTPUT`, and `IO`. Each group is expanded across:

- `LOW` and `HIGH` logic states; and
- `POSITIVE` and `NEGATIVE` polarity.

The plan name template is:

```text
LU_{group.name}_{polarity}_{logic_level}
```

Plan and group overrides adjust selected hold-time and compliance values after the base template is applied.

### Supply plans

Each `POWER` group is expanded across `LOW` and `HIGH` logic states with names such as:

```text
LU_{group.name}_SUPPLY_{logic_level}
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
5. inspect the neutral `GeneratedProject` during integration testing;
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
4. `ProjectGenerationProcessor.process()` creates the neutral project model.
5. `generate_project()` writes the customer project package using the default `LatchUpProjectWriter`.

The example does not import project builders, codecs, or adapter implementation modules. Those details remain behind the supported public API.
