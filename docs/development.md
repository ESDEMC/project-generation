# Development Guide

## Environment

Project Generation requires Python 3.11 or newer. Install the editable package and development dependencies:

```bash
python -m pip install -e ".[dev]"
```

Optional Excel tests or workflows require:

```bash
python -m pip install -e ".[excel]"
```

## Run tests

```bash
pytest
```

The test suite covers definition loading, source and group processing, device states, allocation, ganging, power sequencing, dimensions,
overrides, stress expansion, serialization, diagnostics, schema behavior, and the optional latch-up adapter.

Tests should not depend on the process working directory. Resolve fixtures and examples relative to the test module or repository location.

## Update the JSON Schema

The public schema is generated from `ProjectGenerationDefinition`:

```python
from project_generation import write_json_schema

write_json_schema("project-generation.schema.json")
```

After changing the definition model:

1. regenerate `project-generation.schema.json`;
2. run schema tests;
3. update the format specification and configuration guide;
4. update examples affected by the change; and
5. record user-visible behavior in `CHANGELOG.md`.

## Add a source mapping

Keep customer-specific field names at the definition boundary. Prefer adding or changing a declarative `mapping` over embedding one
customer's field names in core processing code.

Add a core implementation only when the behavior is reusable across definitions, such as a new source type, selector behavior, formatter,
aggregation, allocation strategy, or stress-series form.

## Add a project format

Adapters should consume `GeneratedProject` and produce concrete domain objects or files. They should not modify the semantics of generation
rules after processing.

A future concrete format should subclass `ProjectFormat` and implement `write()`. Recommended format responsibilities:

- enum and type conversion;
- construction of concrete pins, groups, states, plans, and stress objects;
- preservation of generated IDs and relationships;
- customer-format serialization; and
- packaging or manifest creation.

Keep optional format imports isolated so neutral processing remains reusable. The current `LatchUpProjectFormat` is the default used by `generate_project()`.

## Regression tests

For every fixed customer-data issue, add the smallest sanitized fixture that reproduces the behavior. Assert the resolved neutral model,
not only the final serialized text, unless serialization itself is the behavior under test.

Useful assertions include:

- normalized source values;
- deterministic IDs;
- exact group membership and ordering;
- final device-state bias and assignments;
- power sequence order;
- exact generated plan names and dimensions; and
- exact stress-point values.

## Documentation expectations

Changes should update the most specific document:

- `README.md` for project overview or primary workflow changes;
- `docs/configuration.md` for user-facing definition guidance;
- `docs/project-generation-spec.md` for exact format semantics;
- `docs/realis-integration.md` for the supplied customer workflow;
- `docs/customer-delivery.md` for handoff and acceptance changes;
- `CHANGELOG.md` for implemented behavior; and
- `ROADMAP.md` for planned or deferred feature slices.

Avoid duplicating detailed reference material in the README. Link to the authoritative guide instead.
