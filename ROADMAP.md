# Roadmap

The roadmap is intentionally feature-oriented. It is not a commitment to a compiler framework or optimization layer.

## Current foundation

- [x] Parse and validate `generation.json` with Pydantic.
- [x] Load inline, JSON, CSV, and optional Excel pin data.
- [x] Normalize pins and assign deterministic identities.
- [x] Generate explicit and rule-based groups.
- [x] Generate explicit and rule-based test plans.
- [x] Expand dimensions, partitions, overrides, and provisional stress series.
- [x] Resolve device-state inheritance, explicit power domains, and per-group rules.
- [x] Link generated plans to resolved device states.

## Next feature slices

- [x] Resolve power-resource assignments for direct, automatic, and hybrid allocation modes.
- [x] Apply deterministic allocation while respecting reserved and stress resources.
- [x] Add a concrete ganging policy interface and resolve exact same-bias groups together.
- [x] Resolve power-on timing references and produce a deterministic power sequence.
- [x] Resolve power-off timing references with reverse-power-on defaults.
- [x] Improve semantic diagnostics with source paths and definition ownership.
- [x] Add a neutral serialization or inspection format for `GeneratedProject`.
- [x] Build the first adapter to the real latch-up project domain objects.
- [ ] Convert generated stress points into executable `StressPlan` objects using the real domain calculation.
- [ ] Package adapted DUT and test-plan artifacts into a concrete `LatchUpProject` directory.

## Deferred until required by real project behavior

- [ ] Replace the provisional stress-level math with the real domain calculation.
- [ ] Add optimization passes or a formal compiler-stage framework.
- [ ] Add a plugin system for processors or adapters.
- [ ] Migrate away from Pydantic.

- [x] Add a runnable REALIS JSON-to-project package example.
