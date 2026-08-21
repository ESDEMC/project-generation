# Development Guide

[Documentation home](../README.md) · [Package architecture](package-architecture.md)

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

## Update the definition schema and models

The public JSON Schema is authoritative. Definition model structure is generated from `project-generation.schema.json` into
`src/project_generation/definition/generated_models.py`.

When changing the generation-file format:

1. edit `project-generation.schema.json`;
2. rebuild the Pydantic models;
3. run the full test suite;
4. update the format specification and configuration guide;
5. update examples affected by the change; and
6. record user-visible behavior in `CHANGELOG.md`.

Rebuild with:

```bash
python scripts/build_models.py
```

Do not edit `generated_models.py` directly. It is disposable output. `definition/models.py` is the stable facade for handwritten
semantic validation, convenience aliases, and `ProjectGenerationDefinition.load()`. `definition/validation.py` contains diagnostic
validation that does not belong in the structural schema.

`build_models.py` verifies the generated file before accepting it. In addition to compiling the file and checking required classes, it
runs a processing smoke test against the package. If the new generated models break that contract, the previous generated file is
restored and the command fails.

## Add a source mapping

Keep customer-specific field names at the definition boundary. Prefer adding or changing a declarative `mapping` over embedding one
customer's field names in core processing code.

Add a core implementation only when the behavior is reusable across definitions, such as a new source type, selector behavior, formatter,
aggregation, allocation strategy, or stress-series form.

## Add a project writer

Adapters should consume `GeneratedProject` and produce concrete domain objects or files. They should not modify the semantics of generation
rules after processing.

A new concrete project writer should implement `ProjectWriter.write()`. Its infrastructure responsibilities are:

- enum and type conversion;
- construction of concrete pins, groups, states, plans, and stress objects;
- preservation of generated IDs and relationships;
- customer-format serialization; and
- packaging or manifest creation.

Keep concrete writer imports in infrastructure so neutral generation remains reusable. `LatchUpProjectWriter` is the default used by `generate_project()`.

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
- `docs/user/configuration.md` for user-facing definition guidance;
- `docs/reference/project-generation-spec.md` for exact format semantics;
- `docs/real-world/realis.md` for the supplied customer workflow;
- `docs/development/release-checklist.md` for release and delivery-process changes;
- `CHANGELOG.md` for implemented behavior; and
- `ROADMAP.md` for planned or deferred feature slices.

Avoid duplicating detailed reference material in the README. Link to the authoritative guide instead.

## Test organization

The test tree mirrors the package responsibilities rather than keeping every test in one flat directory:

```text
tests/
├── definition/
├── generation/
├── application/
├── infrastructure/
│   ├── latchup_project/
│   └── serialization/
├── architecture/
├── examples/
└── support/
```

Put unit tests beside the corresponding architectural area. Keep customer example execution tests under `tests/examples/`,
and keep shared test-only paths or helpers under `tests/support/`. Test-only definitions should stay in the test suite rather than
being added to `examples/` solely to satisfy tests.

## GitHub Actions CI

The repository includes `.github/workflows/ci.yml`. The workflow runs on pushes to `main`, `master`, and `develop`, on pull requests, and by manual dispatch.

CI tests Python 3.11, 3.12, and 3.13. It verifies that `uv.lock` is current, installs all declared extras with the lockfile held fixed, and runs the complete test suite. A separate job rebuilds the schema-derived Pydantic models and fails if the committed generated model differs from the schema. After those checks pass, CI builds the wheel and source distribution and uploads `dist/` as the `distributions` workflow artifact.

For branch protection, require the three Python test checks and `Generated models are current`. The package build then acts as the final integration check.

