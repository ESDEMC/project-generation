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

## Window layout

The main window follows the standard Qt IDE pattern. The central workspace contains closable `QTabWidget` document tabs plus the Generated Items view, while Project, Parsed Definition, Problems, Parsed Data, and Generation Snapshot are `QDockWidget` tool panes. Qt supplies docking, tabification, moving, floating, and visibility actions for the tool panes. Generated Items opens as a singleton central tab alongside source documents.

Closing a central tab closes only that view. It does not discard the in-memory document or generated state; selecting the item again from the Project tree reopens the tab. The central workspace intentionally does not provide split-pane actions.

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

## Input-file directives

File-backed source paths may use named `str.format` directives such as `path: '{input_file}'`.
The GUI discovers those directives and shows them under **Input Files**. A selected input file is a normal
working-copy document: edits participate in regeneration immediately, while the original file is only changed by
Save or Save All. One directive may feed multiple sources, which is the intended REALIS workflow.

The application-level `bind_input_files()` helper implements the same behavior for headless workflows.
`replace_source_paths()` remains available when a caller specifically wants to replace paths by source name.

## Semantic colors

Generated-data views use a presentation-only `ColorTheme`; generation models do not contain GUI colors. Colors are
looked up in two semantic namespaces:

- pin/group type (`INPUT`, `OUTPUT`, `IO`, `POWER`, `GROUND`, `NC`, and dynamically discovered values);
- hardware assignment (`DC1`, `DC2`, `GROUND`, `FLOATING`, and dynamically discovered values).

The **Tools > Settings… > Colors** page selects a base palette and stores per-value overrides with `QSettings`.
Unknown values receive a deterministic fallback color, and values discovered in generated snapshots are added to the
settings list automatically. The dialog also allows explicit entries to be added for values not present in the current
snapshot.

Normal single-value cells use Qt's standard foreground role. Cells containing mixed semantic values, such as a power
domain with several differently typed groups, use a small `QStyledItemDelegate` backed by Qt rich text so each name can
retain its own type color.
## Editor syntax and validation passes

Text editors use Pygments for language tokenization and Qt's `QSyntaxHighlighter` for rendering. The GUI does not maintain its own YAML or JSON keyword/regex grammar. The same highlighter also overlays find matches without changing the editor cursor.

Generation definitions are processed in distinct passes:

1. parse the working copy as YAML or JSON;
2. validate the parsed value with `ProjectGenerationDefinition`, which is generated from the authoritative JSON Schema;
3. run semantic definition validation;
4. generate the project snapshot.

Referenced YAML/JSON source documents are syntax-checked before generation as well. A syntax failure stops later passes for that regeneration while preserving the last successful snapshot.


## Best-effort generation

The GUI uses `ProjectGenerationProcessor.process_best_effort()` for inspection. A failed generation stage preserves all completed earlier stages and any items produced by the failing stage before the first error. Dependent later stages are marked `not_attempted`. The snapshot carries stage status and diagnostics so an empty collection can be distinguished from a stage that did not run.

Strict `process()` and `process_with_snapshot()` behavior is unchanged and remains the path used for actual project output.
