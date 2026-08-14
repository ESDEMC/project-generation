# Configuration Guide

[Documentation home](../README.md) · [Getting started](getting-started.md) · [Specification](../reference/project-generation-spec.md)

A generation definition describes where project data comes from and how that data is turned into pins, groups, device states, and test plans.
JSON and YAML use the same model, but this guide uses **JSON** so the examples match the focused customer demos.

The complete field behavior is defined in the [format specification](../reference/project-generation-spec.md), and the generated JSON Schema is available at
[`project-generation.schema.json`](../../project-generation.schema.json).

## Top-level structure

A typical definition may contain these sections:

```json
{
  "schema_version": "1.0",
  "project": {},
  "mappings": {},
  "formatters": {},
  "sources": {},
  "dut": {},
  "groups": {},
  "power_resources": {},
  "device_states": {},
  "test_plans": [],
  "test_plan_generation": {}
}
```

You do not need every section. Small projects can be mostly explicit; larger projects can use generation rules for the repetitive parts.

## Schema version

Keep the schema version explicit:

```json
{
  "schema_version": "1.0"
}
```

## Project data

The project name can be written directly:

```json
{
  "project": {
    "name": "Example Project",
    "metadata": {
      "customer": "Example Customer"
    }
  }
}
```

Or project data can come from a named source record:

```json
{
  "project": {
    "source": "realis_project"
  }
}
```

## DUT pins

### Write pins directly

For a small definition, put the pin records inline:

```json
{
  "dut": {
    "name": "Example DUT",
    "pins": {
      "source": {
        "type": "inline",
        "records": [
          {"designator": "1", "name": "VDD", "parameters": {"pin_type": "POWER", "v_max": 5.5}},
          {"designator": "2", "name": "IN_A", "parameters": {"pin_type": "INPUT", "v_max": 5.5}},
          {"designator": "3", "name": "GND", "parameters": {"pin_type": "GROUND"}}
        ]
      }
    }
  }
}
```

### Load pins from a JSON file

If the pins already exist in a customer export, define a source once:

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
    "name": "Customer DUT",
    "pins": {
      "source": "customer_pins"
    }
  }
}
```

Other supported source types are `csv` and `excel` (Excel requires the optional Excel dependency).

## Named mappings

Mappings translate customer values into the values used by generation rules. For example, customer exports might use several labels for the same pin type:

```json
{
  "mappings": {
    "realis_pin_type": {
      "I": "INPUT",
      "Input": "INPUT",
      "O": "OUTPUT",
      "Output": "OUTPUT",
      "IO": "IO",
      "Supply": "POWER",
      "Ground": "GROUND",
      "not connected": "NC"
    }
  }
}
```

Then reference that mapping from a source field:

```json
{
  "mapping": {
    "parameters.pin_type": {
      "from": "PinType",
      "mapping": "realis_pin_type"
    }
  }
}
```

## Formatters

Formatters turn values into reusable text for generated names.

Example conversion:

```text
5.5 -> 5V5
```

The formatter is defined as:

```json
{
  "formatters": {
    "voltage_token": {
      "type": "decimal_token",
      "separator": "V",
      "decimal_places": 1
    }
  }
}
```

A generated name can use that formatter:

```json
{
  "name": {
    "template": "{prefix}{voltage}",
    "fields": {
      "voltage": {
        "source": "partition.parameters.v_max",
        "formatter": "voltage_token"
      }
    }
  }
}
```

## Groups

### Write groups explicitly

Use explicit groups when you already know exactly which pins belong together:

```json
{
  "groups": {
    "explicit": [
      {"name": "SU5V5", "group_type": "POWER", "pins": ["1"]},
      {"name": "IN5V5", "group_type": "INPUT", "pins": ["2", "3"]},
      {"name": "GND", "group_type": "GROUND", "pins": ["5"]}
    ]
  }
}
```

### Generate groups from pin data

Use a generation rule when the same grouping rule applies repeatedly:

```json
{
  "groups": {
    "generation": [
      {
        "id": "groups_by_type_and_voltage",
        "select": {
          "where": {
            "parameters.pin_type": {"in": ["INPUT", "OUTPUT", "POWER"]}
          }
        },
        "group_by": ["parameters.pin_type", "parameters.v_max", "parameters.v_min"],
        "set": {
          "group_type": {"from": "partition.parameters.pin_type"},
          "parameters.v_max": {"from": "partition.parameters.v_max"}
        }
      }
    ]
  }
}
```

### Set generated values

A group rule's `set` object writes resolved values into the generated group. Keys may use dotted paths such as
`parameters.v_max`.

A scalar is a literal value:

```json
{
  "set": {
    "parameters.v_min": 0.0
  }
}
```

Use `from` to resolve a value from the current generation context. A resolved value can also be cast to a basic type:

```json
{
  "set": {
    "group_type": {"from": "partition.parameters.pin_type"},
    "parameters.v_max": {
      "from": "partition.parameters.v_max",
      "cast": "float"
    }
  }
}
```

Supported casts are `float`, `int`, `str`, and `bool`. Mappings and formatters may also be applied to resolved values where
appropriate.

A `set` target can select from ordered conditional alternatives. The first entry whose `when` condition matches is used:

```json
{
  "set": {
    "parameters.compliance_limit": [
      {
        "when": {"partition.parameters.pin_type": "POWER"},
        "value": 0.2
      },
      {
        "when": {
          "partition.parameters.pin_type": {
            "in": ["INPUT", "IO", "OUTPUT"]
          }
        },
        "value": 0.12
      }
    ]
  }
}
```

The conditions use the same path-key matching syntax as selections, device-state rules, and overrides. An alternative without `when` may
be used as the final fallback. If no alternative matches and there is no fallback, that target is omitted rather than being set to
`null`. A literal `null` remains valid when it is explicitly selected.

### Conditional generated-name fields

Name-template fields can also have `when`. If the condition does not match, that field contributes an empty string to the template.
This allows one template to name different group types without creating separate rules:

```json
{
  "name": {
    "template": "{prefix}{voltage}",
    "fields": {
      "prefix": {
        "source": "partition.parameters.pin_type",
        "mapping": "group_type_prefix"
      },
      "voltage": {
        "source": "partition.parameters.v_max",
        "formatter": "voltage_token",
        "when": {
          "partition.parameters.pin_type": {
            "in": ["INPUT", "IO", "OUTPUT"]
          }
        }
      }
    }
  }
}
```

A POWER partition can render only `{prefix}`, while INPUT/IO/OUTPUT partitions include the formatted voltage suffix.

### Mix explicit and generated groups

The two styles can be combined. A common pattern is to keep a special group explicit and generate the repetitive groups:

```json
{
  "groups": {
    "explicit": [
      {"name": "GND", "group_type": "GROUND", "pins": ["5"]}
    ],
    "generation": [
      {
        "id": "signal_and_supply_groups",
        "select": {
          "where": {
            "parameters.pin_type": {"in": ["INPUT", "OUTPUT", "POWER"]}
          }
        },
        "group_by": ["parameters.pin_type", "parameters.v_max"]
      }
    ]
  }
}
```

## Power resources

Power resources describe the logical DC resources generation is allowed to use:

```json
{
  "power_resources": {
    "DC1": {"role": "STRESS"},
    "DC2": {"role": "BIAS"},
    "DC3": {"role": "BIAS"},
    "DC4": {"role": "BIAS"}
  }
}
```

A `STRESS` resource is not automatically used as a normal bias resource.

## Device states

### Assign power domains directly

If the assignments are known, list them explicitly:

```json
{
  "device_states": {
    "logic_high": {
      "power_domains": [
        {
          "name": "ground",
          "groups": ["GND"],
          "assignment": "GROUND",
          "bias": {"mode": "GROUND"}
        },
        {
          "name": "logic_5v5",
          "groups": ["SU5V5", "IN5V5"],
          "assignment": "DC2",
          "bias": {"mode": "VOLTAGE", "level": 5.5}
        }
      ]
    }
  }
}
```

### Let generation allocate bias resources

For larger projects, describe the rules and let the allocator choose from the available resources:

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
            "bias": {
              "mode": "VOLTAGE",
              "level": {"from": "group.v_max"}
            }
          }
        }
      ]
    }
  }
}
```

Allocation modes are `direct`, `automatic`, and `hybrid`.

## Test plans

### Write a test plan explicitly

Use an explicit plan when the test is exceptional or already fully specified:

```json
{
  "test_plans": [
    {
      "name": "IN5V5_HIGH_POSITIVE",
      "test_type": "SIGNAL",
      "dimensions": {"logic_level": "HIGH", "polarity": "POSITIVE"},
      "device_state": "logic_high",
      "test_groups": [
        {
          "group": "IN5V5",
          "stress_points": [
            {"stress_voltage": 5.5, "compliance": 0.1, "hold_time": 0.1},
            {"stress_voltage": 6.0, "compliance": 0.1, "hold_time": 0.1}
          ]
        }
      ]
    }
  ]
}
```

### Generate test plans from a rule

When the same test applies to many groups or settings, generate the combinations:

```json
{
  "test_plan_generation": {
    "rules": [
      {
        "id": "signal_tests",
        "groups": {
          "select": {"where": {"group_type": {"in": ["INPUT", "OUTPUT"]}}},
          "partition": {"mode": "each"}
        },
        "dimensions": [
          {"name": "logic_level", "values": ["LOW", "HIGH"]},
          {"name": "polarity", "values": ["POSITIVE", "NEGATIVE"]}
        ],
        "template": {
          "test_type": "SIGNAL",
          "name": {"template": "{group.name}_{logic_level}_{polarity}"}
        }
      }
    ]
  }
}
```

Three selected groups × two logic levels × two polarities produces 12 plans.

## Stress values

A stress parameter can be written several ways depending on what you need.

### One value

```json
{
  "stress_parameters": {
    "stress_voltage": 5.5,
    "compliance": 0.1
  }
}
```

### List the values directly

```json
{
  "stress_parameters": {
    "stress_voltage": {
      "values": [5.5, 6.0, 6.5]
    }
  }
}
```

### Start from a group value and add offsets

```json
{
  "stress_parameters": {
    "stress_voltage": {
      "from": "group.v_max",
      "add": [0.0, 0.5, 1.0, 1.5]
    }
  }
}
```

For a group with `v_max: 5.0`, that produces `5.0`, `5.5`, `6.0`, and `6.5` V. For a group with `v_max: 3.3`, the same rule produces `3.3`, `3.8`, `4.3`, and `4.8` V.

See [Stress parameters in the specification](../reference/project-generation-spec.md#12-stress-parameters) for the other supported series forms.

## Dimension-specific settings

A dimension value can also change configuration. The following definition starts positive stress from the maximum group voltage and negative stress from the minimum group voltage:

```json
{
  "name": "polarity",
  "values": [
    {
      "value": "POSITIVE",
      "set": {
        "stress_parameters.stress_voltage": {
          "from": "group.v_max",
          "add": [0.0, 0.5, 1.0, 1.5]
        }
      }
    },
    {
      "value": "NEGATIVE",
      "set": {
        "stress_parameters.stress_voltage": {
          "from": "group.v_min",
          "add": [0.0, -0.5, -1.0, -1.5]
        }
      }
    }
  ]
}
```

## Overrides

Overrides are for exceptions to the normal rule.

Change every negative plan:

```json
{
  "scope": "plan",
  "when": {"polarity": "NEGATIVE"},
  "set": {"stress_parameters.hold_time": 0.075}
}
```

Change only negative OUTPUT groups:

```json
{
  "scope": "group",
  "when": {"group.group_type": "OUTPUT", "polarity": "NEGATIVE"},
  "set": {"stress_parameters.compliance": 0.025}
}
```

These entries go in the rule's `overrides` array and are applied in declaration order.

## Choosing explicit or generated configuration

You do not have to choose one style for the whole file:

| If... | Prefer... |
| --- | --- |
| The exact pins/groups/plans are already known | Explicit JSON entries |
| The same rule repeats across many pins/groups/tests | Generation rules |
| Most things follow a rule but a few are special | Generated rules plus explicit entries or overrides |

The focused demos under [`examples/customizing_generation/`](../../examples/customizing_generation) show each of these patterns in complete files.
