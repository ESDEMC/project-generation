# Changelog

All notable changes to this package are tracked here while the declarative generation format is being developed.

## Unreleased

- Build real latch-up `StressPlan` and `StressParameters` objects from generated stress points.
- Map stress level, compliance, hold time, source mode, pulse base, pulse delay, and measurement timing into the adapted test plan.

### Added

- Deterministic power-off sequences with reverse-power-on defaults.
- Explicit `timing.power_off.after` dependencies and per-step delays.
- Neutral `GeneratedProject` serialization through `generated_project_to_dict`, `generated_project_to_json`, and `write_generated_project`.
- Validation for unknown, self-referential, and circular power-off timing dependencies.

- Deterministic power-on sequences compiled from named power-domain timing.
- Dependency ordering through `timing.power_on.after` with per-step delays.
- Validation for unknown timing references, self-references, duplicate inherited domain names, and circular dependencies.

- Explicit `GangingPolicy` abstraction with `none` and `same_voltage` implementations.
- Deterministic same-bias reuse of automatically and explicitly assigned physical power resources.
- Validation for unsupported ganging-policy names.
- Neutral per-group power assignments on generated device states.
- Direct, automatic, and hybrid power-resource allocation.
- Deterministic `first_available` and provisional `voltage_first` allocation ordering.
- Validation for unknown resources, unassigned direct-mode groups, unsupported strategies, and insufficient resources.
- Automatic exclusion of reserved resources and resources with the `STRESS` role.
- Neutral generated device states with deterministic IDs.
- Resolution of explicit power domains to generated group identities.
- Per-group device-state rule evaluation with support for group parameter references.
- Device-state inheritance through `extends`.
- Resolved `device_state_id` references on generated test plans.
- Validation failures for unknown device-state references, unknown power-domain groups, and circular inheritance.
- `ROADMAP.md` for feature-oriented planning.

### Changed

- External-group power domains can participate in generated power sequences even when group UUIDs are intentionally unavailable.

- `GeneratedProject` now contains `device_states` in addition to pins, groups, and test plans.
- Tests that load examples resolve paths relative to the test files rather than the current working directory.

## 0.1.0 - Initial implementation

### Added

- Pydantic definitions for `generation.json`.
- Generated JSON Schema and example validation.
- Inline, JSON, CSV, and optional Excel pin sources.
- Pin normalization and deterministic pin identities.
- Explicit and rule-generated groups with deterministic identities.
- Explicit and generated test plans.
- Dynamic dimensions, partitions, ordered overrides, exclusions, and provisional stress-series expansion.

## Unreleased

- Build real latch-up `StressPlan` and `StressParameters` objects from generated stress points.
- Map stress level, compliance, hold time, source mode, pulse base, pulse delay, and measurement timing into the adapted test plan.

### Added

- Added `LatchUpProjectCoreAdapter` and `adapt_to_latchup_project()` as the first concrete adapter.
- Added lazy conversion to the real `latchup-project-core` `Dut`, `PinGroup`, `DeviceState`, `PowerSequence`, and
  `LatchUpTestPlan` domain objects.
- Preserved generated IDs, group membership, plan dimensions, device-state assignments, and power timing references.
- Preserved provisional stress points in test-plan metadata until the real stress-plan calculation is implemented.
- Added optional integration tests against the supplied latch-up domain packages.

- Added a runnable REALIS JSON-to-latch-up-project example that writes normalized generation definitions and packaged project artifacts.
