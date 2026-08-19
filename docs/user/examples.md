# Project Generation Examples

[Documentation home](../README.md) · [Getting started](getting-started.md) · [REALIS real-world example](../real-world/realis.md)

The examples are organized by **what an end user is trying to do**. Each example keeps its generation definition beside the Python file that uses it.

## Recommended learning path

| Example | What you learn |
| --- | --- |
| [Explicit project](../../examples/basics/explicit_project/generate_project.py) | Write a small project directly in JSON and generate it. |
| [JSON pin source](../../examples/sources/json_pin_source/generate_project.py) | Replace inline pins with records loaded from a customer JSON file. |
| [Spreadsheet pin source](../../examples/sources/spreadsheet_pin_source/generate_project.py) | Load and map pins from an Excel workbook using a path relative to the generation file. |
| [Group generation](../../examples/customizing_generation/group_generation/demo.py) | Generate repetitive pin groups from pin metadata. |
| [Device states and power allocation](../../examples/customizing_generation/device_states_and_power_allocation/demo.py) | Define bias rules and let generation choose DC resources. |
| [Test-plan dimensions](../../examples/customizing_generation/test_plan_dimensions/demo.py) | Generate combinations of groups, logic levels, and polarities. |
| [Stress series and overrides](../../examples/customizing_generation/stress_series_and_overrides/demo.py) | Generate stress levels from group values and make exceptions. |
| [Hardware configuration source](../../examples/sources/hardware_config/demo.py) | Use `hardware.yaml` as the physical source for device-state power allocation. |
| [REALIS real-world example](../../examples/real_world/realis/generate_projects.py) | Apply one maintained definition to multiple real customer-style exports. |

## 1. Explicit project

Directory: `examples/basics/explicit_project/`

Start here. Pins, groups, device state, and the test plan are written directly.

An explicit group looks like:

```json
{
  "groups": {
    "explicit": [
      {"name": "IN5V5", "group_type": "INPUT", "pins": ["2"]}
    ]
  }
}
```

An explicit test plan looks like:

```json
{
  "test_plans": [
    {
      "name": "IN5V5_HIGH_POSITIVE",
      "test_type": "SIGNAL",
      "device_state": "logic_high",
      "test_groups": [
        {
          "group": "IN5V5",
          "stress_points": [
            {"stress_voltage": 5.5, "compliance": 0.1, "pulse_width": 0.1}
          ]
        }
      ]
    }
  ]
}
```

Run:

```bash
python examples/basics/explicit_project/generate_project.py
python examples/basics/explicit_project/validate_definition.py
```

## 2. External JSON pin source

Directory: `examples/sources/json_pin_source/`

The rest of the project stays explicit; only the pin input changes. Instead of copying the pins into `generation.json`, point at the customer file and map its fields:

```json
{
  "sources": {
    "customer_pins": {
      "type": "json",
      "path": "./data/customer-device.json",
      "select": "$.pins[*]",
      "mapping": {
        "designator": "pin_number",
        "name": "signal_name",
        "parameters.pin_type": "latch_up_type",
        "parameters.v_max": "v_max",
        "parameters.v_min": "v_min"
      }
    }
  },
  "dut": {
    "pins": {"source": "customer_pins"}
  }
}
```

Run:

```bash
python examples/sources/json_pin_source/generate_project.py
```

Relative source paths are resolved from the directory containing the generation file.

## 3. External spreadsheet pin source

Directory: `examples/sources/spreadsheet_pin_source/`

The spreadsheet source uses the same record-mapping model as JSON and CSV sources:

```yaml
sources:
  customer_pins:
    type: excel
    path: ./data/customer-device.xlsx
    sheet: Pins
    mapping:
      designator: pin_number
      name: signal_name
      parameters.pin_type: latch_up_type
      parameters.v_max: v_max
      parameters.v_min: v_min
```

The `path` above is interpreted relative to `generation.yaml`, regardless of the process working directory.

Run:

```bash
python examples/sources/spreadsheet_pin_source/generate_project.py
```

## 4. Customizing generation

These demos each isolate one kind of customization.

### 4.1 Group generation

Directory: `examples/customizing_generation/group_generation/`

Instead of writing every group by hand, select pins and group them by metadata:

```json
{
  "groups": {
    "generation": [
      {
        "id": "groups_by_type_and_voltage",
        "select": {
          "where": {"parameters.pin_type": {"in": ["INPUT", "OUTPUT", "POWER"]}}
        },
        "group_by": ["parameters.pin_type", "parameters.v_max", "parameters.v_min"],
        "set": {
          "group_type": {"from": "partition.parameters.pin_type"},
          "parameters.v_max": {"from": "partition.parameters.v_max"},
          "parameters.v_min": {"from": "partition.parameters.v_min"}
        },
        "name": {
          "template": "{prefix}{voltage}",
          "fields": {
            "prefix": {
              "source": "partition.parameters.pin_type",
              "mapping": "group_type_prefix"
            },
            "voltage": {
              "source": "partition.parameters.v_max",
              "formatter": "voltage_token"
            }
          }
        }
      }
    ]
  }
}
```

For the demo input, that rule produces:

```text
SU5V5  -> VDD
IN5V5  -> IN_A, IN_B
OUT3V3 -> OUT_A
GND    -> GND (explicit)
```

`IN_A` and `IN_B` are together because both are `INPUT` pins with the same voltage. `GND` is defined separately.

```bash
python examples/customizing_generation/group_generation/demo.py
```

### 4.2 Device states and power allocation

Directory: `examples/customizing_generation/device_states_and_power_allocation/`

Reserve `DC1` for stress, then let the allocator choose bias resources for the groups that match the rules:

```json
{
  "device_states": {
    "logic_high": {
      "allocation": {
        "mode": "hybrid",
        "strategy": "voltage_first",
        "reserve": ["DC1"],
        "ganging_policy": "same_voltage"
      },
      "rules": [
        {
          "when": {"group.group_type": {"in": ["POWER", "INPUT"]}},
          "set": {
            "bias": {"mode": "VOLTAGE", "level": {"from": "group.v_max"}}
          }
        }
      ]
    }
  }
}
```

```bash
python examples/customizing_generation/device_states_and_power_allocation/demo.py
```

### 4.3 Test-plan dimensions

Directory: `examples/customizing_generation/test_plan_dimensions/`

One rule can generate each group at every requested logic-level/polarity combination:

```json
{
  "dimensions": [
    {"name": "logic_level", "values": ["LOW", "HIGH"]},
    {"name": "polarity", "values": ["POSITIVE", "NEGATIVE"]}
  ],
  "template": {
    "test_type": "SIGNAL",
    "name": {"template": "{group.name}_{logic_level}_{polarity}"}
  }
}
```

With three selected groups, this produces `3 × 2 × 2 = 12` plans.

```bash
python examples/customizing_generation/test_plan_dimensions/demo.py
```

### 4.4 Stress series and overrides

Directory: `examples/customizing_generation/stress_series_and_overrides/`

Generate stress levels relative to each group's own operating limit:

```json
{
  "stress_parameters.stress_voltage": {
    "from": "group.v_max",
    "add": [0.0, 0.5, 1.0, 1.5]
  }
}
```

Then describe exceptions instead of copying the whole plan:

```json
{
  "overrides": [
    {
      "scope": "plan",
      "when": {"polarity": "NEGATIVE"},
      "set": {"stress_parameters.pulse_width": 0.075}
    },
    {
      "scope": "group",
      "when": {"group.group_type": "OUTPUT", "polarity": "NEGATIVE"},
      "set": {"stress_parameters.compliance": 0.025}
    }
  ]
}
```

```bash
python examples/customizing_generation/stress_series_and_overrides/demo.py
```

## 4. REALIS real-world example

Directory: `examples/real_world/realis/`

REALIS intentionally combines multiple capabilities because that is the actual workflow. The maintained definition is YAML, but it uses the same fields shown in the JSON examples above.

```bash
python examples/real_world/realis/generate_projects.py
```

Process selected exports:

```bash
python examples/real_world/realis/generate_projects.py path/to/device-a.json path/to/device-b.json \
    --output-directory build/realis-projects
```

See [REALIS real-world example](../real-world/realis.md) for the complete workflow.

## Output directory

Examples that write files use `./generated` by default unless documented otherwise. Override it with `PROJECT_GENERATION_OUTPUT_DIRECTORY`.
