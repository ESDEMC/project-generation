import pathlib
import runpy

import pytest

ROOT = pathlib.Path(__file__).parents[1]
EXAMPLES = ROOT / "examples"


@pytest.mark.parametrize(
    ("script_path", "expected_patterns"),
    [
        (EXAMPLES / "neutral_project" / "generate_project.py", ("**/*.generated.json",)),
        (
            EXAMPLES / "customer_project" / "generate_project.py",
            ("**/*.generated.json", "**/*.Prj", "**/*.LuDut", "**/*.LuTstPlan"),
        ),
        (EXAMPLES / "multiple_neutral_projects" / "generate_projects.py", ("**/*.generated.json",)),
        (
            EXAMPLES / "explicit_test_plan_project" / "generate_project.py",
            ("**/*.Prj", "**/*.LuDut", "**/*.LuTstPlan"),
        ),
        (
            EXAMPLES / "latchup_project" / "generate_project.py",
            ("**/*.Prj", "**/*.LuDut", "**/*.LuTstPlan"),
        ),
        (
            EXAMPLES / "multiple_latchup_projects" / "generate_projects.py",
            ("**/*.Prj", "**/*.LuDut", "**/*.LuTstPlan"),
        ),
        (
            EXAMPLES / "realis" / "generate_single_project.py",
            ("**/*.Prj", "**/*.LuDut", "**/*.LuTstPlan"),
        ),
    ],
    ids=lambda value: value.stem if isinstance(value, pathlib.Path) else None,
)
def test_generation_example_writes_expected_artifacts(
    script_path: pathlib.Path,
    expected_patterns: tuple[str, ...],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
) -> None:
    output_directory = tmp_path / "generated"
    monkeypatch.setenv("PROJECT_GENERATION_OUTPUT_DIRECTORY", str(output_directory))
    runpy.run_path(str(script_path), run_name="__main__")

    for pattern in expected_patterns:
        assert list(output_directory.glob(pattern)), f"{script_path} did not produce {pattern}"
