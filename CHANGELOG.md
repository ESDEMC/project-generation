# Changelog

## Unreleased

- Moved device-state compliance requirements into group `bias_spec` definitions instead of inferring limits from `group_type`.
- Ganged bias specifications now merge `compliance_limit` using the maximum requested value; other conflicting concrete bias fields remain incompatible.

### Breaking changes

- Simplified generated device states around `PowerDomain` as the canonical bias/allocation model.
- Removed generated `GroupState` and `PowerAssignment` objects.
- Moved baseline bias requirements onto groups as `bias_spec`.
- Device-state rules now modify only `bias_spec`; the previous rule-level `assignment` and `bias` fields are no longer part of the normal automatic flow.
- Removed the `direct` / `automatic` / `hybrid` allocation-mode switch. Allocation configuration now contains only policy fields: `strategy`, `reserve`, and `ganging_policy`.
- Ganging now operates only on compatible bias specifications and no longer knows about or reuses DC-resource assignments.

### Added

- Added dedicated generation modules for device states, group generation, source loading, value resolution, and power sequencing.

### Changed

- Device-state generation now follows a single pipeline: effective group bias specs -> ganging -> merged bias -> source selection -> `PowerDomain`.
- State inheritance carries effective per-group bias specs and re-runs ganging/source selection instead of inheriting generated assignments.
- Missing bias mode defaults to `VOLTAGE` when a numeric bias level is present.
- `GROUND` and `FLOATING` remain pseudo-resources and do not consume physical DC sources.
- Hardware compatibility checks run against the merged domain bias, including its declared `compliance_limit`.
- `processor.py` was split into focused generation modules and reduced to pipeline coordination.
- Power-sequence semantics are unchanged; sequence generation continues to operate on the generated power domains.
- Updated examples and documentation to use group `bias_spec` and domain-centric device-state output.

### Fixed

- Restored flattened group parameters in device-state rule context after the processor split. This includes `group.v_max`.
