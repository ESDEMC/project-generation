# Package architecture

[Documentation home](../README.md) · [Development guide](development.md)

The package uses architectural layer names only where they describe a real dependency boundary. The inner project-generation concepts keep domain-specific names (`definition` and `generation`) instead of being hidden inside a generic `core` package.

```text
project_generation/
├── __init__.py
├── diagnostics.py
├── definition/
│   ├── generated_models.py       Generated from project-generation.schema.json
│   ├── models.py                 Stable facade and semantic model behavior
│   └── validation.py             Diagnostic definition validation
├── generation/
│   ├── models.py
│   ├── processor.py
│   ├── rules.py
│   ├── ganging.py
│   └── validation.py
├── application/
│   ├── ports.py
│   └── workflows.py
└── infrastructure/
    ├── serialization/
    │   └── generated_project_json.py
    └── latchup_project/
        ├── writer.py
        ├── latchup_adapter.py
        ├── dut.py
        ├── latchup_test_plan.py
        └── latchup_project_core/
```

## `definition`

`definition` owns the project-generation input language.

Put code here when it describes or validates what a user can declare in a generation JSON/YAML file, for example:

- the authoritative `project-generation.schema.json` structure;
- generated Pydantic definition models;
- source, rule, mapping, state, or power-resource configuration;
- handwritten semantic model behavior; and
- semantic/diagnostic validation of a definition.

It should not know how a generated project is serialized or written for Latch-Up.

The definition model split is intentional:

```text
project-generation.schema.json
        ↓  scripts/build_models.py
src/project_generation/definition/generated_models.py
        ↓
src/project_generation/definition/models.py
```

`generated_models.py` contains structural Pydantic classes and may be replaced at any time. `models.py` imports the generated classes,
defines stable aliases/unions used by the rest of the package, and subclasses the generated root model to add handwritten semantic
behavior, including `load()`. Code outside `definition` should normally import definition types from `definition.models`, not directly from
`generated_models`.

## `generation`

`generation` is the neutral project-generation domain. It converts a valid definition into `GeneratedProject` and related generated models.

Put code here for:

- pins and groups;
- dimension/rule expansion;
- partitioning;
- power assignment and ganging;
- device states;
- generated test plans and stress points;
- validation of generated identities and references.

This is deliberately not called `core` or `domain`. `generation` is more precise about the capability it contains.

## `application`

`application` contains use-case coordination and ports needed by those use cases. It should remain thin.

`ports.py` defines `ProjectWriter`: the contract used when a generated neutral project must be written to an external representation. The interface belongs here because the application depends on the capability, while infrastructure supplies its implementation.

`workflows.py` contains small operations that coordinate existing project-generation concepts, such as replacing source paths and converting diagnostics into the public exception model.

Do not put file-format implementation details, JSON codecs, or Latch-Up project classes here.

## `infrastructure`

`infrastructure` contains adapters and implementations that cross the neutral project-generation boundary.

### `infrastructure/serialization`

Neutral JSON serialization belongs here because writing JSON is an external representation concern, not part of the generated-project model itself.

### `infrastructure/latchup_project`

This package contains the concrete integration with the Latch-Up project representation:

- `LatchUpProjectWriter`;
- conversion from `GeneratedProject` to Latch-Up objects;
- Latch-Up project/DUT/test-plan model support;
- project package builders/codecs.

The default `generate_project()` workflow uses `LatchUpProjectWriter`, but `generation` has no dependency on it.

## Dependency direction

The important rule is that dependencies point inward:

```text
                 definition
                     ↓
                 generation
                     ↑
                 application
                     ↑
               infrastructure
```

More concretely:

- `generation` may depend on `definition` and shared diagnostics where necessary;
- `application` may depend on `definition` and `generation`;
- `infrastructure` may depend on `application` ports and `generation` models;
- `definition` and `generation` must not import `application` or `infrastructure`.

The test suite contains an architecture-boundary test for the last rule.

## Public imports

Normal callers and examples should import the supported API from the package root:

```python
from project_generation import generate_project, load_project_definition
```

A custom external writer implements the application port:

```python
from project_generation import ProjectWriter
```

Code implementing infrastructure may import the relevant internal application/generation types directly.

## Where should new code go?

Use this decision order:

1. Does it define something users can declare in a generation file? Put it in `definition`.
2. Does it calculate or represent the neutral generated project? Put it in `generation`.
3. Does it coordinate a use case or define a capability that external code must provide? Put it in `application`.
4. Does it read/write an external representation or integrate with a concrete project implementation? Put it in `infrastructure`.
5. Is it an error/diagnostic type genuinely shared across those boundaries? `diagnostics.py` is appropriate.

Avoid adding generic packages unless a future responsibility cannot be named more precisely. In particular, avoid catch-all names:

```text
core
common
utils
output
formats
extensions
```
