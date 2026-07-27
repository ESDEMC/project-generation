# Customer Delivery Guide

A customer delivery should be reproducible from a known generation definition, known source exports, and a known package revision. Generated
files should not be treated as manually maintained source files.

## Delivery contents

A complete handoff should include the items appropriate to the contract and customer environment:

```text
delivery/
├── README.md                    Customer-specific run and import instructions
├── generation/                 Approved generation definitions
├── schema/                     Matching JSON Schema, when definitions are customer-editable
├── source-examples/            Sanitized examples, when permitted
├── generated-projects/         Final project packages
├── reports/                    Validation and review records
└── version.txt                 Package/repository revision used for generation
```

Do not include raw customer exports in a general documentation package unless the delivery agreement explicitly requires them.

## Recommended release workflow

### 1. Freeze inputs

Record:

- the exact generation definition;
- the exact customer source files or source-system export revision;
- the Project Generation package version or Git commit;
- the latch-up domain package versions used by the adapter; and
- the command used to create the output.

### 2. Validate the definition

Run the repository tests and validate the delivery definition:

```bash
pytest
```

```python
from project_generation import load_project_definition, raise_for_diagnostics, validate_project_definition

definition = load_project_definition("path/to/generation.yaml")
raise_for_diagnostics(validate_project_definition(definition))
```

### 3. Generate neutral inspection output

Write a neutral JSON result for each representative customer input. This creates a reviewable boundary before concrete file packaging.

```python
from project_generation import ProjectGenerationProcessor, write_generated_project

project = ProjectGenerationProcessor().process(definition, base_directory=definition_directory)
write_generated_project(project, "reports/generated-project.json")
```

When a wrapper script performs source substitution, use that same wrapper for inspection or record the substituted definition used for the
run.

### 4. Review generated content

Review at least:

- project name and retained metadata;
- pin count, designators, names, and types;
- group count, names, types, voltages, and membership;
- device-state inheritance and final per-group bias;
- physical assignments, reserved resources, and ganging;
- power-on and power-off order and delays;
- plan count and naming;
- device-state reference for every plan;
- stress polarity, levels, compliance, timing, and source mode; and
- output file names and package manifest references.

Automated count checks are useful, but they do not replace engineering review of electrical intent.

### 5. Generate customer files

Run the approved adapter and package builder. For the included REALIS workflow:

```bash
python examples/realis/generate_projects.py path/to/customer-export.json \
    --definition path/to/approved-generation.yaml \
    --output-directory path/to/delivery/generated-projects
```

Generate into a clean directory to prevent obsolete artifacts from a previous run from being delivered.

### 6. Perform acceptance checks

Recommended acceptance checks include:

- every project package opens in the target application;
- every manifest reference resolves to an included file;
- the DUT and all test plans deserialize successfully;
- expected plan counts match the approved rule expansion;
- no unexpected `.bak`, temporary, cache, or debug files are included;
- a representative project can be inspected in the customer application; and
- checksums are captured after final packaging when required by the delivery process.

### 7. Document known limitations

State any behavior that remains provisional, intentionally deferred, or dependent on a customer assumption. Do not hide unresolved mapping
questions inside a generation rule.

## Customer-facing README template

The delivery README should identify:

1. what the package contains;
2. the supported customer application version;
3. how the projects were generated;
4. how to import or open them;
5. which source export and generation-definition revisions were used;
6. validation performed before delivery;
7. known limitations or assumptions; and
8. the support contact and issue-reporting information.

Avoid exposing internal repository paths or developer-only setup unless the customer is expected to run generation themselves.

## When the customer will run generation

Provide the customer with:

- a pinned Python environment or packaged executable;
- the approved generation definition;
- the matching JSON Schema;
- a clear input-directory and output-directory convention;
- a command that does not depend on the developer's working directory;
- examples containing no confidential third-party data;
- validation and diagnostic instructions; and
- an upgrade policy for schema or package changes.

A customer-operated workflow should fail clearly on unknown mappings or invalid source data rather than silently producing a partially
correct project.

## Change control

Treat changes to these items as delivery-impacting:

- source mappings;
- group partitioning or naming;
- device-state bias rules;
- allocation or ganging behavior;
- power timing;
- plan dimensions or overrides;
- stress calculations; and
- adapter or package serialization.

Record behavior changes in `CHANGELOG.md`, update the relevant guide, and add or update a regression test using sanitized data.
