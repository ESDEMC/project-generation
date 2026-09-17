
## Unreleased

- Use Qt Advanced Docking System for the application workspace and persist/restore window geometry and dock layout.
- Open generated Pins, Groups, Device States, Hardware Envelopes, and Test Plans as individual ADS tabs outside the document workspace.
- Isolate source-document tabs in a dedicated nested ADS manager so only documents occupy the central document workspace and tool/generated docks cannot enter it.
- Update the REALIS negative signal voltage sweep to 0.25x and 0.5x of the voltage span.
# Changelog
- Exposed each generated group's authored bias as `group.bias` in test-plan rule context for SIGNAL and SUPPLY generation.

- Improved stress-pair plot visibility with high-contrast connector/marker halos and explicit foreground layering.

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
- Added stress resources to generated device states as empty-group stress-bus power domains and included them in power-on and power-off sequences.

### Changed

- Device-state generation now follows a single pipeline: effective group bias specs -> ganging -> merged bias -> source selection -> `PowerDomain`.
- Removed unused duplicate generation modules left behind by the processor split; value resolution remains in `values.py`, while input and test-plan coordination remain in `processor.py`.
- Grouped device-state compilation and hardware support into dedicated `generation.device_states` and `generation.hardware` packages.
- State inheritance carries effective per-group bias specs and re-runs ganging/source selection instead of inheriting generated assignments.
- Missing bias mode defaults to `VOLTAGE` when a numeric bias level is present.
- `GROUND` and `FLOATING` remain pseudo-resources and do not consume physical DC sources.
- Hardware compatibility checks run against the merged domain bias, including its declared `compliance_limit`.
- `processor.py` was split into focused generation modules and reduced to pipeline coordination.
- Power-sequence semantics are unchanged; sequence generation continues to operate on the generated power domains.
- Updated examples and documentation to use group `bias_spec` and domain-centric device-state output.

### Fixed

- Restored flattened group parameters in device-state rule context after the processor split. This includes `group.v_max`.
