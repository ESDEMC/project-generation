# Project Generation

Project Generation is a Python package for turning declarative project definitions and structured customer data into generated test
projects. The current default target is the Latch-Up project format, but generation logic is intentionally separated from concrete project
writers so additional targets can be added later.

This README is the **developer entry point** for the repository. End-user documentation starts at
[`docs/README.md`](docs/README.md).

## Repository goals

The package is designed to keep three concerns separate:

1. **What the user declares** — sources, groups, device states, test-plan rules, stress rules, and overrides.
2. **What Project Generation calculates** — normalized pins, generated groups, assignments, states, plans, and stress points.
3. **How the result is delivered** — conversion and serialization into a concrete project package such as Latch-Up.

The important architectural rule is that concrete project formats must not leak back into the generation model.

## Package architecture

```text
src/project_generation/
├── definition/                  Generation-file models and definition validation
├── generation/                  Generated models, rules, processing, allocation, and validation
├── application/                 Use-case coordination and external capability ports
├── infrastructure/
│   ├── serialization/           External serialization implementations
│   └── latchup_project/         Default Latch-Up writer and concrete project integration
└── diagnostics.py               Shared structured diagnostics
```

The intended dependency direction is:

```text
definition  <-  generation  <-  application  <-  infrastructure
```

In practice, `application` coordinates generation and defines ports. One of those ports is:

```text
ProjectWriter
```

Infrastructure implements those ports.
The inner `definition` and `generation` packages must not depend on application or infrastructure code.

See [`docs/development/package-architecture.md`](docs/development/package-architecture.md) for the detailed placement rules.

## Development setup

Project Generation requires Python 3.11 or newer.

```bash
python -m pip install -e ".[dev]"
```

Optional Excel source support:

```bash
python -m pip install -e ".[excel]"
```

Run the test suite from the repository root:

```bash
pytest
```

The test tree mirrors the package responsibilities:

```text
tests/
├── definition/
├── generation/
├── application/
├── infrastructure/
│   ├── latchup_project/
│   └── serialization/
├── architecture/
├── documentation/
├── examples/
├── fixtures/
└── support/
```

When adding tests, put them in the corresponding architectural area. Test-only generation definitions belong under `tests/fixtures/`,
not under `examples/`.

## Main development workflow

A typical change should follow this order:

1. Change the most specific implementation area (`definition`, `generation`, `application`, or `infrastructure`).
2. Add or update tests in the matching test package.
3. If the generation-file format changed, edit `project-generation.schema.json` and rebuild the definition models with `python scripts/build_models.py`.
4. Update the relevant end-user documentation and focused example if behavior visible to users changed.
5. Update [`CHANGELOG.md`](CHANGELOG.md).

The development guide has more detail: [`docs/development/development.md`](docs/development/development.md).

## Public workflow

The primary end-user API is intentionally small:

```python
from project_generation import generate_project

project_path = generate_project("generation.json", "generated")
```

`generate_project()` processes the generation definition and then delegates delivery to a `ProjectWriter`. If no writer is supplied,
`LatchUpProjectWriter` is used.

For definition validation without generation:

```python
from project_generation import load_project_definition, validate_project_definition
from project_generation.application.workflows import raise_for_diagnostics

definition = load_project_definition("generation.json")
raise_for_diagnostics(validate_project_definition(definition))
```

Normal examples and application code should prefer imports from `project_generation` rather than reaching into implementation modules.

## Adding generation behavior

Use the responsibility of the behavior to decide where it belongs:

| Change | Location |
|---|---|
| New generation-file field or declaration | `definition/` |
| New grouping, partitioning, allocation, stress, or plan-generation behavior | `generation/` |
| New use-case coordination or external capability contract | `application/` |
| New concrete project writer, codec, or external representation | `infrastructure/` |
| Shared structured generation error/diagnostic | `diagnostics.py` |

Avoid generic dumping grounds when the responsibility can be named more precisely. Names to avoid include:

```text
core
common
utils
formats
output
extensions
```

## Adding a project writer

A concrete writer implements the `ProjectWriter` port and consumes the generated project model. It should translate the already-resolved
generation result into the target representation; it should not introduce new generation semantics.

The current default implementation is:

```text
infrastructure/latchup_project/
```

Its responsibilities include converting generated pins/groups/states/plans into Latch-Up types and writing the final package artifacts.

See [`docs/development/development.md`](docs/development/development.md#add-a-project-writer) for the implementation expectations.

## Examples

Examples are intentionally **end-user oriented**. They are not a second test-fixture directory or a place to demonstrate internal models.
The current catalog covers:

- basic project generation and definition validation;
- loading pins from an external JSON source;
- customizing group generation;
- customizing device states and power allocation;
- customizing test-plan dimensions;
- customizing stress series and overrides; and
- the REALIS real-world workflow.

Start at [`examples/README.md`](examples/README.md) or the fuller [`docs/user/examples.md`](docs/user/examples.md).

## Documentation layout

| Document | Audience / purpose |
|---|---|
| [`docs/README.md`](docs/README.md) | End-user documentation home |
| [`docs/user/getting-started.md`](docs/user/getting-started.md) | First project generation workflow |
| [`docs/user/configuration.md`](docs/user/configuration.md) | How to write generation definitions |
| [`docs/user/examples.md`](docs/user/examples.md) | Focused runnable examples |
| [`docs/real-world/realis.md`](docs/real-world/realis.md) | Real-world REALIS workflow |
| [`docs/user/diagnostics.md`](docs/user/diagnostics.md) | Validation and troubleshooting |
| [`docs/development/release-checklist.md`](docs/development/release-checklist.md) | Maintainer release and delivery checklist |
| [`docs/reference/project-generation-spec.md`](docs/reference/project-generation-spec.md) | Exact generation-format semantics |
| [`docs/development/package-architecture.md`](docs/development/package-architecture.md) | Internal package boundaries |
| [`docs/development/development.md`](docs/development/development.md) | Developer conventions and extension guidance |

Relative Markdown links are used throughout the repository so the documentation remains usable when the delivery folder is moved.
Documentation tests verify local links and fenced JSON examples.

## Schema changes

`project-generation.schema.json` is the source of truth for the public generation-file structure. The Pydantic definition models are
generated from that schema; do not hand-edit `src/project_generation/definition/generated_models.py`.

After changing the schema, rebuild the definition models:

```bash
python scripts/build_models.py
```

The build script generates a temporary model file, checks that the required definition classes exist, installs the generated file, and
runs an import/processing smoke test. If verification fails, the previous generated model file is restored.

Handwritten behavior that is not purely structural belongs in `src/project_generation/definition/models.py` or
`src/project_generation/definition/validation.py`, not in the generated file. After rebuilding, run the full test suite and update the
configuration/specification docs and examples for any user-visible format change.

## Project status

Implemented changes are recorded in [`CHANGELOG.md`](CHANGELOG.md). Planned or deferred work belongs in
[`ROADMAP.md`](ROADMAP.md).
