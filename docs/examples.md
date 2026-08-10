# Project generation examples

Each runnable example is self-contained. The Python script, generation definition, and any source data used by that definition are stored in the same example directory. This makes an example easy to copy, modify, or deliver without resolving paths into another example folder.

All commands in this guide are run from the repository root—the directory containing `pyproject.toml`, `README.md`, `docs/`, and `examples/`. The executable examples remain under the top-level `examples/` directory; `docs/` contains documentation only.

On Windows PowerShell, first change to the repository root:

```powershell
Set-Location D:\Python\project-generation
python .\examples\neutral_project\generate_project.py
```

By default, generated files are written beneath `./generated`. Set `PROJECT_GENERATION_OUTPUT_DIRECTORY` to place output elsewhere.

```bash
PROJECT_GENERATION_OUTPUT_DIRECTORY=build/examples \
    python examples/neutral_project/generate_project.py
```

On Windows PowerShell:

```powershell
$env:PROJECT_GENERATION_OUTPUT_DIRECTORY = "build/examples"
python examples/neutral_project/generate_project.py
```

## Neutral generated project

Directory: `examples/neutral_project/`

```text
neutral_project/
├── generate_project.py
└── generation.json
```

```bash
python examples/neutral_project/generate_project.py
```

The script loads its adjacent `generation.json` and writes the complete neutral `GeneratedProject` as JSON.

## Customer rule-generated project

Directory: `examples/customer_project/`

```text
customer_project/
├── data/
│   └── customer-device.json
├── generate_project.py
└── generation.json
```

```bash
python examples/customer_project/generate_project.py
```

This example uses the default Latch-Up project writer to create the concrete package, then also writes the neutral model as an optional inspection artifact.


## Explicit test-plan project

Directory: `examples/explicit_test_plan_project/`

```bash
python examples/explicit_test_plan_project/generate_project.py
```

This example uses an adjacent generation definition containing an explicitly authored latch-up test plan. It calls the public `generate_project()` API and writes the default `.Prj`, `.LuDut`, and `.LuTstPlan` package artifacts.

## One latch-up project package

Directory: `examples/latchup_project/`

```bash
python examples/latchup_project/generate_project.py
```

The script calls `generate_project()` with no writer argument. The default `LatchUpProjectWriter` writes `.Prj`, `.LuDut`, and `.LuTstPlan` artifacts.

## Multiple latch-up project packages

Directory: `examples/multiple_latchup_projects/`

```bash
python examples/multiple_latchup_projects/generate_projects.py
```

The script processes both local definitions through the default `LatchUpProjectWriter` and writes each latch-up project into its own package directory.

## REALIS source data

Directory: `examples/realis/`

```text
realis/
├── input/
├── generate_projects.py
└── generation.yaml
```

Generate a project for every local export:

```bash
python examples/realis/generate_projects.py
```

Specific files and an output directory can also be supplied:

```bash
python examples/realis/generate_projects.py path/to/device-a.json path/to/device-b.json \
    --output-directory build/realis-projects
```

All REALIS scripts use the adjacent `generation.yaml` and only the public `project_generation` API.

## Validation and inspection

These supporting examples also keep their definition beside the script:

```bash
python examples/validate_definition/validate_definition.py
python examples/inspect_project/inspect_project.py
```

Every Python example is discovered recursively and executed by `tests/test_public_examples.py`. The test suite also verifies that generation scripts have a co-located JSON or YAML definition.
