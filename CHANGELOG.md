# Changelog
- Added generated test-plan temperature control and wired the REALIS project temperature metadata into each Latch-Up test plan.
- Added conditional grouping fields for selected group types, and updated REALIS to keep non-voltage group names unsuffixed while using a local hardware source.

All notable changes to Project Generation are recorded here.

The project is still under active development. Until the public generation format is declared stable, changes under `Unreleased` may
include structural changes to the package, examples, and generation definition.


## Unreleased

- Set the REALIS signal and supply stress pulse width to a consistent 10 ms default.
- Allow `dut.name` to use literals, direct value references, or templates composed from parsed project data and metadata.
- Resolve relative source paths from the directory containing the generation definition.
- Add `examples/sources/spreadsheet_pin_source` with an Excel-backed pin source example.
- Standardize biased-pulse stress terminology on `pulse_width`; `hold_time` remains a legacy input alias only.

- Added structured power-resource resolution reporting with candidate rejection reasons, aggregate unresolved groups, and user-facing formatting for hardware compatibility failures.
- Updated REALIS examples to source physical power resources from `examples/sources/hardware_config/hardware.yaml` and demonstrate hardware-incompatible device-state rejection.

### Added

- Added `hardware.source` so generation can use the runtime `hardware.yaml` as the physical power-resource source.
- Added hardware-aware device-state allocation and validation using connection mode and DC power envelopes.
- Added validation that hardware-backed `power_resources` overlays cannot invent resources that are not physically connected.

## 0.2.0 - Aug 10, 2026

### Added

- Added `generate_project()` as the primary public workflow for generating a concrete project package.
- Added the `ProjectWriter` application port so additional project-package implementations can be added without changing generation
  logic.
- Added `LatchUpProjectWriter` as the default concrete writer used by `generate_project()`.
- Added conversion from generated project data to Latch-Up DUT, device-state, power-sequence, test-plan, and stress-plan objects.
- Added deterministic generated device states and per-group power assignments.
- Added direct, automatic, and hybrid power-resource allocation.
- Added `first_available` and `voltage_first` allocation strategies.
- Added reserved-resource and `STRESS`-role exclusion during automatic allocation.
- Added `none` and `same_voltage` ganging policies.
- Added device-state inheritance with `extends`.
- Added deterministic power-on and power-off sequence generation, including `after` dependencies and per-step delays.
- Added validation for invalid power-sequence references, self-references, duplicate inherited domain names, and dependency cycles.
- Added generated stress points and Latch-Up `StressPlan`/`StressParameters` construction.
- Added named test-plan template fields with per-field mappings and formatters, matching generated group-name behavior.
- Added the REALIS real-world example for generating projects from customer-style JSON exports.
- Added customer documentation for getting started, configuration, examples, diagnostics, REALIS usage, and delivery.
- Added developer documentation for package architecture and development conventions.
- Added documentation tests that verify relative Markdown links and parse fenced JSON snippets.
- Added architecture-boundary tests for the inner `definition` and `generation` packages.
- Added `ROADMAP.md` for planned and intentionally deferred work.

### Changed

- Reorganized the package into responsibility-based modules:
  - `definition/` for the generation-file schema and definition validation;
  - `generation/` for generated models, rules, processing, allocation, ganging, and generated-model validation;
  - `application/` for use-case coordination and external capability ports; and
  - `infrastructure/` for concrete serialization and Latch-Up project integration.
- Removed generic architectural package names in favor of explicit responsibilities (`formats`, `output`, and `extensions` were removed).
- Renamed the concrete output abstraction from `ProjectFormat` to `ProjectWriter` and the default implementation to
  `LatchUpProjectWriter`.
- Reorganized the test suite to mirror the package architecture instead of keeping tests in a flat directory.
- Moved test-only generation definitions into `tests/fixtures/` instead of using customer examples as implicit test fixtures.
- Reorganized examples around end-user tasks instead of historical implementation variants.
- Consolidated duplicate examples into a smaller end-user-oriented catalog:
  - basic explicit project generation and validation;
  - external JSON pin sources;
  - group-generation customization;
  - device-state and power-allocation customization;
  - test-plan dimension customization;
  - stress-series and override customization; and
  - the REALIS real-world workflow.
- Removed internal/intermediate-model demos that were not useful to end users.
- Removed redundant per-example README files; `examples/README.md` and `docs/user/examples.md` now provide the example catalog while each
  runnable Python demo explains itself with a module docstring.
- Reworked demo docstrings to show concrete input/output behavior using compact tables and mappings.
- Added focused generation-file snippets to runnable demo docstrings so users can see the configuration that causes each result.
- Reorganized documentation into `user/`, `real-world/`, `reference/`, and `development/` subfolders.
- Standardized documentation examples so illustrative data is shown in blocks or tables instead of embedded inline in prose.
- Updated customer-facing documentation to show JSON snippets when explaining alternative ways to write generation definitions.
- Kept YAML examples in the REALIS guide where they correspond to the actual `generation.yaml` file.
- Updated REALIS test-plan names to use compact logic/polarity tokens (`H+`, `L+`, `H-`, `L-`) while preserving semantic dimension values.
- Updated example scripts and tests to use the reorganized example paths.
- Updated example output to favor simple, user-readable group-to-pin summaries.
- Made package-root imports avoid eagerly importing the concrete Latch-Up infrastructure where possible.
- External-group power domains can participate in generated power sequences even when group UUIDs are intentionally unavailable.

### Fixed

- Fixed stale example and test paths left by earlier project reorganization.
- Fixed example tests whose behavior depended on the current working directory.
- Fixed a missing `StressPoint` import introduced when generation code was split into modules.
- Fixed example execution so pytest command-line arguments are not unintentionally passed through to runnable examples.
- Fixed generation examples so output directories are created when needed.
- Fixed documentation references after reorganizing and removing duplicate examples.

## 0.1.0 - Initial implementation

### Added

- Pydantic definitions for `generation.json`.
- Generated JSON Schema and example validation.
- Inline, JSON, CSV, and optional Excel pin sources.
- Pin normalization and deterministic pin identities.
- Explicit and rule-generated groups with deterministic identities.
- Explicit and generated test plans.
- Dynamic dimensions, partitions, ordered overrides, exclusions, and provisional stress-series expansion.

### Hardware stress capability resolution

- Added rich hardware-domain objects for operating points, DC/PULSE envelopes, supply capabilities, and biased-pulse stress.
- Added the `source_switch` stress strategy. It validates the pre/post bias against the stress source's `DC` envelopes and the stress peak against its `PULSE` envelopes.
- Generated test plans now retain the resolved stress resource and strategy.
- Added structured stress-supply resolution diagnostics suitable for CLI and desktop UI reporting.

- Model DC and PULSE supply capabilities as distinct hardware-domain envelopes. Source Switch stress validation now checks pre/post bias
  against DC envelopes and checks peak operating point plus pulse width against one complete PULSE envelope. Updated the shared
  `examples/sources/hardware_config/hardware.yaml` to the richer Source Switch capability data.
