# Project Generation GUI

The GUI is an interactive workbench for project-generation definitions. It uses `qtpy` and keeps the headless `project_generation` package independent of Qt.

## First iteration

The first vertical slice provides:

- opening JSON or YAML generation definitions;
- automatic discovery of ordinary file-backed source and hardware files;
- one editor document per canonical filesystem path;
- live regeneration from the in-memory contents of all open documents;
- no writes to the project directory until **Save** or **Save All**;
- retained last-successful `GenerationSnapshot` when the current working copy is invalid;
- parsed-definition and generation-snapshot trees;
- a structured Problems table;
- dirty-state indicators on editor tabs.

`GenerationSnapshot` is produced by `ProjectGenerationProcessor.process_with_snapshot()` and contains the effective definition, generated pins, groups, device states, test plans, and final `GeneratedProject` from the same generation pass.

## Running

Install the GUI extra with the project and run:

```text
project-generation-gui path/to/generation.yaml
```

The implementation imports Qt only through `qtpy`. The `gui` extra currently installs PyQt5 as the default Qt binding.

## Working-copy semantics

Editing an open document only changes its `TextDocument.text` value. A debounced regeneration uses those current in-memory contents. To preserve the existing processor's normal filesystem contract, the GUI materializes the working copy into a temporary generation workspace and processes that workspace.

The original project directory is only modified by explicit save operations.

This separation is intentional:

```text
Editor working copy ──► temporary generation workspace ──► GenerationSnapshot
        │
        └──────────────► real file only on Save / Save All
```

## Next iteration

The next slice should add the schema-driven inspector and dynamic reference controls. Those controls should modify the same document working copy rather than directly mutating Pydantic objects.
