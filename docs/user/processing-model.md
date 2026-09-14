# Processing Model

[Documentation home](../README.md) · [Configuration](configuration.md) · [Specification](../reference/project-generation-spec.md)

Project Generation behaves like a deterministic compiler: it loads a declarative definition, resolves it against source data, validates
cross-references, and produces the project files required by the selected generation workflow.

## Pipeline

```text
Generation definition
        │
        ▼
Load source records
        │
        ▼
Normalize pins and source values
        │
        ▼
Create explicit and generated groups
        │
        ▼
Resolve group bias specs, power domains, and power allocation
        │
        ▼
Create and expand test plans
        │
        ▼
Validate resolved project content
        │
        ▼
Write the final project package
```

## Deterministic identities

Pins, groups, device states, and test plans receive deterministic identities derived from their resolved content and ownership context.
Processing the same definition and source data should therefore produce stable references and ordering.

Stable identities are important for:

- reproducible customer deliveries;
- comparison of generated results between releases;
- linking plans to device states and groups;
- reviewing changes caused by source-data updates; and
- regression testing.

## Source normalization

Source-specific names and values should be normalized as early as possible. Record mappings move source fields into the internal shape,
and named mappings translate source vocabularies into normalized values.

A source may contain more than one label for the same meaning:

```text
I     -> INPUT
Input -> INPUT
```

Normalizing both values to the same result prevents later group and test-plan rules from containing source-specific special cases.

## Group generation

Group processing occurs after pins are normalized. Explicit groups resolve their pin references directly. Generation rules select pins,
partition them by configured fields, derive group values, and render group names.

A generated value may be literal, resolved from the current partition/context, cast to a basic type, or selected from ordered conditional
alternatives. Conditional alternatives use the same matching DSL as selections and overrides; the first matching alternative wins. If no
alternative matches and there is no fallback, that target is omitted. Name fields may also be conditional; a nonmatching field contributes
an empty string to the template.

Member aggregation can derive a single group value from all pins in a partition. The final group retains concrete pin IDs rather than the
original source selectors.

## Device-state resolution

Device-state processing deliberately follows the canonical power model:

```text
Group.bias_spec
      ↓
Apply device-state bias_spec rules
      ↓
Gang compatible group specs
      ↓
Merge and complete the domain bias
      ↓
Select a compatible DC source
      ↓
GeneratedPowerDomain
```

A group owns its baseline, possibly incomplete, bias requirement. Device-state rules modify only `bias_spec`; there is no generated
per-group state or separate power-assignment model. `PowerDomain` is the canonical generated representation of groups that are biased
together by one source with one concrete configuration.

Compliance is authored in each group `bias_spec`. When compatible groups are ganged, `compliance_limit` is merged using the maximum
requested value. Python does not infer compliance from `group_type`. Hardware compatibility is checked against the merged domain bias.

Inheritance carries effective group bias specs, then re-runs ganging and source selection for the child state. This prevents a parent's
chosen source from becoming an accidental requirement of the child.

## Power sequence compilation

Named power domains may define timing dependencies. Power-on steps are topologically ordered from `after` references while preserving
declaration order where no dependency requires a different order.

When no explicit power-off timing is defined, shutdown defaults to the reverse of the resolved power-on sequence. Explicit power-off
`after` dependencies can define another valid shutdown graph.

Missing references, self-references, duplicate inherited domain names, and circular timing dependencies fail processing.

## Test-plan expansion

Test-plan generation follows this order:

1. select candidate groups;
2. partition them using `each`, `group_by`, or `all`;
3. expand configured dimensions;
4. apply dimension-specific field settings;
5. build the plan template;
6. apply ordered plan-level overrides;
7. resolve group-level values and exclusions;
8. apply ordered group-level overrides;
9. expand concrete stress points; and
10. resolve the referenced device state.

This ordering is significant. Later overrides can intentionally replace values produced by the template or earlier overrides.

## Generated project package

After the rules are resolved and validated, the configured writer creates the final project package. With the default Latch-Up writer, the
output contains the DUT definition, generated test plans, project manifest, and the relationships required by the target application.

The writer preserves the resolved project content produced by the earlier stages, including group membership, device-state power domains,
power timing, dimensions, and stress plans.

For an end-to-end example of generating customer files, see the [REALIS real-world example](../real-world/realis.md).
