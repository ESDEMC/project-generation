# Project Generation Documentation

This directory is the documentation entry point for Project Generation.

Project Generation turns a declarative generation definition and source data into a validated generated project. The default writer produces a Latch-Up project package.

## Customer documentation

Start here when installing, configuring, running, reviewing, or accepting a delivered project-generation workflow.

| Guide | Use it for |
| --- | --- |
| [Getting started](user/getting-started.md) | Install the package and generate the first project. |
| [Configuration guide](user/configuration.md) | Configure sources, pins, groups, device states, power resources, and test-plan generation. |
| [Examples](user/examples.md) | Run the supplied examples and inspect their expected outputs. |
| [REALIS real-world example](real-world/realis.md) | Generate Latch-Up projects from REALIS JSON exports. |
| [Processing model](user/processing-model.md) | Understand how a definition becomes a deterministic generated project. |
| [Diagnostics and validation](user/diagnostics.md) | Understand validation failures and structured generation diagnostics. |
| [Project Generation specification](reference/project-generation-spec.md) | Reference the exact declarative behavior and precedence rules. |

Useful repository files:

- [JSON Schema](../project-generation.schema.json) — machine-readable schema for generation definitions.
- [Runnable examples](../examples/README.md) — self-contained Python examples and local input data.
- [REALIS generation definition](../examples/real_world/realis/generation.yaml) — complete shared customer-data example.
- [Changelog](../CHANGELOG.md) — implemented behavior by release.

## Maintainer documentation

These documents are primarily for developers extending or maintaining the package:

- [Package architecture](development/package-architecture.md)
- [Development guide](development/development.md)
- [Release checklist](development/release-checklist.md)
- [Roadmap](../ROADMAP.md)

## Documentation navigation

All repository links are relative. Keep the repository or delivery folder structure intact when copying the documentation so links continue to resolve.

Markdown links can point directly to other Markdown files, Python files, JSON/YAML definitions, schemas, images, PDFs, or other local files. For example:

```markdown
[Configuration guide](user/configuration.md)
[JSON Schema](../project-generation.schema.json)
[REALIS definition](../examples/real_world/realis/generation.yaml)
```

Use forward slashes in relative links, even on Windows. Avoid machine-specific absolute paths in delivered documentation.

Do not use paths like:

```text
C:\Projects\...
```
