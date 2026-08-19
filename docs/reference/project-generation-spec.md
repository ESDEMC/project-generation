# Project Generation Specification

[Documentation home](../README.md) · [Configuration](../user/configuration.md) · [Processing model](../user/processing-model.md)

## 1. Purpose

This package defines a declarative project-generation format for compiling customer data into concrete DUT, pin-group, device-state, power-sequence, and test-plan domain objects.

The declarative definition describes what should be generated. The compiler owns loading, normalization, selection, grouping, allocation, expansion, validation, and serialization.

The compiled project must contain no unresolved queries, dimensions, formatters, allocation strategies, overrides, or stress-series definitions.

## 2. Design principles

1. Pins are compiled once and retain stable identities.
2. Groups reference compiled pins; they do not recreate them.
3. Declarative definitions and compiled runtime objects are separate models.
4. Test-plan dimensions are dynamic and are not hard-coded as logic level, polarity, temperature, or any other customer-specific concept.
5. Test-group selection and partitioning are separate from dimension expansion.
6. Device states may be named globally or declared inline.
7. Explicit assignments are resolved before automatic allocation.
8. Automatic behavior is selected by named strategies implemented in Python.
9. Overrides are ordered, visible, and deterministic.
10. Stress-parameter series use domain-oriented array and range operations rather than arbitrary expressions.
11. Scalars broadcast across stress points; array-valued parameters zip by position.
12. Cartesian stress-parameter products are never implicit.
13. The compiler reports structured diagnostics and supports dry-run inspection.
14. JSON Schema validates structure; compiler validation enforces semantic correctness.

## 3. Compilation pipeline

```text
ProjectGenerationDefinition
        ↓
Load source records
        ↓
Normalize pin declarations
        ↓
Compile DUT pins with stable identities
        ↓
Generate or load pin groups
        ↓
Format and validate group names
        ↓
Resolve named device-state definitions
        ↓
Select and partition test groups
        ↓
Expand arbitrary test-plan dimensions
        ↓
Apply dimension value settings
        ↓
Apply matching plan overrides
        ↓
Resolve power domains and assignments
        ↓
Resolve per-group stress-parameter definitions
        ↓
Expand stress series into concrete stress points
        ↓
Validate concrete test plans
        ↓
Write project artifacts
```

## 4. Top-level definition

A project-generation definition may contain:

- project metadata
- reusable constants
- reusable mappings and formatters
- data sources
- DUT and pin definitions
- group-generation rules
- logical power resources
- named device states
- explicit test plans
- test-plan generation rules
- output configuration

Illustrative structure:

```json
{
  "schema_version": "1.0",
  "project": {},
  "constants": {},
  "mappings": {},
  "formatters": {},
  "sources": {},
  "dut": {},
  "groups": {},
  "hardware": null,
  "power_resources": {},
  "device_states": {},
  "test_plans": [],
  "test_plan_generation": {},
  "output": {}
}
```

## 4.1 Hardware-backed power resources

The optional `hardware` section references the runtime hardware configuration used to constrain device-state power assignments.

```yaml
hardware:
  source: hardware.yaml
```

The source path is relative to the generation definition. `power_supply.hardware_connections[].matrix_assignment` defines the available
resource names. `mode: bias` resources are eligible for normal bias allocation and `mode: switch` resources are treated as stress
resources. `metadata.power_supply[].power_envelopes.DC` supplies the DC capability envelope.

If `hardware` is present, every explicit physical assignment and every automatically allocated assignment must exist in the loaded
hardware configuration and support the requested bias. Explicit `power_resources` entries act only as overlays for resources that exist
in hardware; they cannot introduce an unconnected physical resource.

## 5. Sources and record normalization

### 5.1 Supported sources

Initial source adapters:

- inline records
- JSON
- CSV
- Excel

Every source normalizes to:

```python
Iterable[Mapping[str, object]]
```

### 5.2 JSON selection

JSON sources may use a deliberately small JSONPath-style selector, for example:

```json
{
  "type": "json",
  "path": "./device.json",
  "select": "$.pins[*]"
}
```

Complex filtering belongs to compiler selection rules rather than the source loader.

### 5.3 Record mapping

Source fields map into normalized pin fields:

```json
{
  "mapping": {
    "designator": "pin_number",
    "name": "signal_name",
    "parameters.pin_type": "latch_up_type",
    "parameters.v_max": "v_max"
  }
}
```

Named converters may normalize values. Arbitrary Python expressions are not part of the public format.

## 6. Stable identities

Pins should receive deterministic identifiers. A recommended implementation is UUID5 derived from stable source identity and pin designator.

```python
uuid.uuid5(namespace, f"{device_key}:{designator}")
```

Generated groups and plans may use deterministic identifiers derived from their semantic keys.

## 7. Group generation

### 7.1 Selection and grouping

Group rules select normalized pins and group them by one or more fields.

```json
{
  "where": {
    "parameters.pin_type": {
      "equals": "OUTPUT"
    }
  },
  "group_by": [
    "parameters.v_max"
  ]
}
```

Initial query operators:

- equals
- not_equals
- in
- exists

### 7.2 Group-name generation

Group names are generated from known group properties rather than parsed after creation.

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
        "formatter": "voltage_token"
      }
    }
  }
}
```

Reusable mappings and formatters are declared globally.

```text
mapping   -> value to value
formatter -> value to text
cast      -> basic runtime type conversion
```

A name field may include `when`. The condition uses the normal matching DSL. If it does not match, the field renders as an empty string;
source resolution, mapping, and formatting are skipped for that field.

### 7.3 Generated value assignment

The `set` object on a group-generation rule writes values into the generated group. Dotted keys create nested paths.

A scalar value is literal:

```json
{
  "set": {
    "parameters.v_min": 0.0
  }
}
```

A resolver object may obtain the value from generation context:

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

Resolver objects support `from` or `value`, plus optional `aggregate`, `mapping`, `formatter`, `cast`, and `when` fields where those
operations are meaningful. Supported `cast` values are `float`, `int`, `str`, and `bool`.

A target may contain an ordered list of resolver/value definitions. Such a list is interpreted as conditional alternatives when its
items are value-definition objects. The first alternative whose `when` predicate matches is selected. An item without `when` is an
unconditional fallback. If no item matches and no fallback exists, the target is omitted. Omission is distinct from explicitly resolving
the literal value `null`.

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

Ordinary literal arrays remain arrays; a list is not automatically treated as conditional alternatives merely because it is a list.

## 8. Power resources and device states

### 8.1 Logical power resources

Power resources describe logical assignments rather than hardware addresses.

```text
DC1
DC2
DC3
```

A resource may carry capabilities or constraints used by allocation strategies.

### 8.2 Device states

Device states may be globally named and referenced by test plans or generated dimension values.

```json
{
  "device_states": {
    "logic_low": {},
    "logic_high": {}
  }
}
```

Inline states may extend named states.

```json
{
  "device_state": {
    "extends": "logic_high"
  }
}
```

### 8.3 Power domains

Power domains are the units that receive logical power-resource assignments.

```json
{
  "name": "logic_5v5",
  "groups": ["SU5V5", "IN5V5"],
  "assignment": "DC2",
  "bias": {
    "mode": "VOLTAGE",
    "level": 5.5
  }
}
```

A domain naturally models ganging.

### 8.4 Assignment modes

Device-state definitions may use direct, automatic, or hybrid allocation.

Direct mode is appropriate when assignments are already known:

```json
{
  "allocation": {"mode": "direct"},
  "power_domains": [
    {
      "name": "logic_5v5",
      "groups": ["SU5V5", "IN5V5"],
      "assignment": "DC2",
      "bias": {"mode": "VOLTAGE", "level": 5.5}
    }
  ]
}
```

Automatic mode lets the selected strategy choose assignments:

```json
{
  "allocation": {
    "mode": "automatic",
    "strategy": "voltage_first",
    "reserve": ["DC1"]
  }
}
```

Hybrid mode keeps explicit assignments and automatically fills the rest:

```json
{
  "allocation": {
    "mode": "hybrid",
    "strategy": "voltage_first",
    "reserve": ["DC1"],
    "ganging_policy": "same_voltage"
  },
  "power_domains": [
    {
      "name": "ground",
      "groups": ["GND"],
      "assignment": "GROUND",
      "bias": {"mode": "GROUND"}
    }
  ]
}
```

Hybrid assignment resolves explicit assignments first, then runs the selected allocation strategy for remaining groups.

### 8.5 Allocation and ganging

Named strategies remain implemented in Python. The initial strategy may reserve the stress resource, assign supply groups first, assign static-bias groups, then assign remaining signal groups.

Ganging is a separate policy rather than hidden inside the assignment strategy.

Initial policies:

- none
- same_voltage

### 8.6 Timing

Timing is associated with power domains and compiles into a concrete power sequence.

```json
{
  "timing": {
    "power_on": {
      "delay": 0.005,
      "after": "supply_28v"
    }
  }
}
```

The compiler emits the device state and power sequence as separate concrete objects.

## 9. Test groups and partitioning

A generated test plan contains a collection of test groups. There is no general `stress_group` field in the generation model.

The generator first selects eligible groups, then partitions them.

```text
All groups
    ↓ selection
Eligible groups
    ↓ partitioning
Test-group partitions
    ↓ dimension expansion
Concrete test plans
```

Initial partition modes:

### Each

```json
{
  "partition": {
    "mode": "each"
  }
}
```

### Group by fields

```json
{
  "partition": {
    "mode": "group_by",
    "fields": ["group_type", "v_max"]
  }
}
```

### All

```json
{
  "partition": {
    "mode": "all"
  }
}
```

The singular formatter context `group` is available only when a partition contains exactly one group. General contexts include `groups`, `group_count`, `group_names`, and `partition`.

## 10. Dynamic dimensions

Dimensions are arbitrary named axes used to expand plan candidates.

```json
{
  "dimensions": [
    {
      "name": "logic_level",
      "values": ["LOW", "HIGH"]
    },
    {
      "name": "polarity",
      "values": ["POSITIVE", "NEGATIVE"]
    }
  ]
}
```

A value may use compact or expanded form.

```json
{
  "value": "HIGH",
  "set": {
    "device_state": "logic_high"
  }
}
```

Dimension settings are merged in declaration order.

## 11. Overrides

Overrides handle exceptions and interactions between dimensions, partitions, and groups.

```json
{
  "when": {
    "logic_level": "HIGH",
    "polarity": "NEGATIVE"
  },
  "set": {
    "device_state": "logic_high_negative"
  }
}
```

Initial override actions:

- set
- exclude

Overrides are evaluated in declaration order. A later matching override wins for fields it sets.

An override may be plan-scoped or group-scoped. Group-scoped overrides are evaluated independently for each test group after the plan candidate is expanded.

### Resolution precedence

1. Global defaults by test type.
2. Rule template.
3. Partition-derived context.
4. Dimension value settings in dimension order.
5. Matching plan-scoped overrides in declaration order.
6. Group-derived stress-parameter generation.
7. Matching group-scoped overrides in declaration order.
8. Explicit per-group values.
9. Semantic validation.

## 12. Stress parameters

### 12.1 Concrete output

Regardless of declaration style, the compiler emits explicit stress parameters for each test group and each stress point.

```json
{
  "group": "IN5V5",
  "stress_points": [
    {
      "stress_voltage": 5.5,
      "compliance": 0.1,
      "pulse_width": 0.1
    },
    {
      "stress_voltage": 6.0,
      "compliance": 0.1,
      "pulse_width": 0.1
    }
  ]
}
```

### 12.2 Supported series forms

#### Scalar

```json
{
  "compliance": 0.1
}
```

#### Explicit values

```json
{
  "stress_voltage": {
    "values": [5.5, 6.0, 6.5]
  }
}
```

#### Numeric range by step

```json
{
  "stress_voltage": {
    "range": {
      "start": 5.5,
      "stop": 7.0,
      "step": 0.5
    }
  }
}
```

#### Numeric range by number of points

```json
{
  "stress_voltage": {
    "range": {
      "start": 5.5,
      "stop": 7.0,
      "num": 4
    }
  }
}
```

`num` means the number of resulting points, including both endpoints.

#### Base multiplied by factors

```json
{
  "stress_voltage": {
    "from": "group.v_max",
    "multiply_by": [1.0, 1.1, 1.2]
  }
}
```

#### Base plus offsets

```json
{
  "stress_voltage": {
    "from": "group.v_max",
    "add": [0.0, 0.5, 1.0]
  }
}
```

#### Relative factor or offset ranges

```json
{
  "stress_voltage": {
    "from": "group.v_max",
    "factor_range": {
      "start": 1.0,
      "stop": 1.3,
      "step": 0.1
    }
  }
}
```

```json
{
  "stress_voltage": {
    "from": "group.v_max",
    "offset_range": {
      "start": 0.0,
      "stop": 1.5,
      "step": 0.5
    }
  }
}
```

Only one series-generation mode may be selected for a parameter definition.

### 12.3 Array combination

- Scalar parameters broadcast to every stress point.
- Array-valued parameters zip by position.
- Non-scalar arrays must have equal lengths.
- Cartesian products are not implicit.
- Product support should be deferred until a concrete requirement exists.

### 12.4 Dimension-dependent stress parameters

Dimension values may set stress-parameter definitions.

```json
{
  "value": "POSITIVE",
  "set": {
    "stress_parameters.stress_voltage": {
      "from": "group.v_max",
      "add": [0.0, 0.5, 1.0]
    }
  }
}
```

Combination overrides may replace or refine these definitions.

## 13. Explicit and generated plans

A fully explicit plan lists the final groups and stress points directly:

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
            {"stress_voltage": 5.5, "compliance": 0.1},
            {"stress_voltage": 6.0, "compliance": 0.1}
          ]
        }
      ]
    }
  ]
}
```

A generated plan describes the repeating rule instead:

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
          {"name": "polarity", "values": ["POSITIVE", "NEGATIVE"]}
        ],
        "template": {
          "test_type": "SIGNAL",
          "name": {"template": "{group.name}_{polarity}"}
        }
      }
    ]
  }
}
```

Both can appear in the same definition when most tests follow a rule but a few tests are special. Overrides provide another way to handle small exceptions without copying an entire plan.

## 14. Concrete compiled model

The compiled model must be simple and directly executable.

```python
@dataclass(frozen=True, kw_only=True)
class GeneratedProject:
    dut: Dut
    test_plans: tuple[TestPlan, ...]
    diagnostics: GenerationDiagnostics
```

A concrete test plan contains:

- concrete test groups
- concrete device state
- concrete power domains
- concrete assignments
- concrete bias configurations
- concrete power sequence
- concrete per-group stress points

## 15. Diagnostics

Every compiler pass may emit structured diagnostics.

Suggested diagnostic fields:

```python
@dataclass(frozen=True, kw_only=True)
class GenerationDiagnostic:
    severity: DiagnosticSeverity
    code: str
    message: str
    location: DefinitionLocation | None
    context: Mapping[str, object]
```

Initial diagnostic codes should include:

- GROUP_NAME_DUPLICATE
- DEVICE_STATE_NOT_FOUND
- POWER_RESOURCE_ALREADY_ASSIGNED
- GROUP_LEFT_FLOATING
- STRESS_SERIES_LENGTH_MISMATCH
- OVERRIDE_MATCHED_NOTHING
- TEST_PLAN_DUPLICATE
- PARTITION_FIELD_MISSING
- GROUP_SELECTION_EMPTY
- INVALID_STRESS_PARAMETER

Diagnostics should preserve enough context to explain automatic decisions and dry-run results.

## 16. Validation responsibilities

### JSON Schema

JSON Schema validates:

- required properties
- property types
- enums and discriminators
- supported variant structures
- mutually exclusive series modes where practical

### Compiler validation

Compiler validation checks:

- referenced sources, groups, states, mappings, and resources exist
- partition fields exist on selected groups
- override conditions reference available dimensions or context fields
- generated plan names and semantic keys are unique
- power assignments are compatible
- required test-type parameters are present
- stress-series array lengths are compatible
- generated plans contain at least one test group
- concrete plans are executable by the existing runtime domain

## 17. Implementation passes

Recommended compiler passes:

1. Source loading
2. Pin normalization and compilation
3. Group generation
4. Device-state definition resolution
5. Test-group selection and partitioning
6. Dynamic dimension expansion
7. Plan override application
8. Device-state and power-domain planning
9. Per-group stress-parameter resolution
10. Stress-series expansion
11. Concrete-plan validation
12. Artifact writing

Intermediate processing objects should remain inspectable and independently testable. Current examples include:

```text
GroupPartition
TestPlanCandidate
PlannedDeviceState
```

## 18. Initial implementation slices

### Slice 1: Fully explicit generation

- inline pins
- explicit groups
- explicit device states and power domains
- explicit test plans
- explicit stress points
- project writer

### Slice 2: Pin and group generation

- JSON and CSV sources
- record mappings and named converters
- selection and grouping
- group-name formatters

### Slice 3: Test-plan rule expansion

- group selection
- each, group_by, and all partitioning
- dynamic dimensions
- dimension value settings
- set and exclude overrides
- name formatting

### Slice 4: Stress-series generation

- scalars
- explicit arrays
- ranges using step or num
- offsets and factors
- offset and factor ranges
- broadcasting and zipped arrays

### Slice 5: Device-state planning

- named and inline states
- extends
- explicit domains
- timing defaults and overrides
- concrete power-sequence compilation

### Slice 6: Automatic allocation

- reserve stress resource
- explicit assignments first
- supply groups first
- static-bias groups next
- signal groups last
- same-voltage ganging
- logic-low grounding
- unresolved groups floating with diagnostics

## 19. Deferred features

Version 1 should defer:

- arbitrary mathematical expressions
- arbitrary Python plugins referenced by JSON
- implicit Cartesian parameter products
- a large general-purpose query language
- deep inheritance chains
- automatic optimization across all possible power assignments
- arbitrary override operations

## 20. Decision register

1. Pins are compiled once and groups reference them.
2. Pin identities are deterministic.
3. Declarative and compiled models are separate.
4. Sources only load records; filtering belongs to compiler selection.
5. Group names are generated from known properties.
6. Reusable mappings and formatters are globally named.
7. Power resources are logical, not hardware addresses.
8. Power domains are the assignment and ganging unit.
9. Direct, automatic, and hybrid device-state planning are supported.
10. Ganging is an explicit policy separate from assignment strategy.
11. Test plans contain `test_groups`; one-plan-per-group is only a partition strategy.
12. Partitioning supports each, group_by, and all.
13. Dimensions are dynamic and customer-defined.
14. Dimension values may set plan fields, including device state and stress parameters.
15. Overrides support `set` and `exclude` and are ordered.
16. Plan-scoped and group-scoped overrides are supported.
17. Stress parameters may be shared definitions but always compile into concrete per-group stress points.
18. Stress series support values, ranges, offsets, factors, offset ranges, and factor ranges.
19. Scalars broadcast; arrays zip; products are not implicit.
20. JSON Schema validates structure; Python validates semantics.
21. Every significant compiler pass emits structured diagnostics.
22. Representative examples are part of the specification and acceptance suite.
