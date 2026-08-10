import pathlib
import runpy
import sys

import pytest

from tests.support.paths import EXAMPLES


@pytest.mark.parametrize(
    ("script_path", "expected_patterns"),
    [
        (
            EXAMPLES / "basics" / "explicit_project" / "generate_project.py",
            ("**/*.Prj", "**/*.LuDut", "**/*.LuTstPlan"),
        ),
        (
            EXAMPLES / "sources" / "json_pin_source" / "generate_project.py",
            ("**/*.Prj", "**/*.LuDut", "**/*.LuTstPlan"),
        ),
        (
            EXAMPLES / "real_world" / "realis" / "generate_projects.py",
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
    monkeypatch.setattr(sys, "argv", [str(script_path)])
    runpy.run_path(str(script_path), run_name="__main__")

    for pattern in expected_patterns:
        assert list(output_directory.glob(pattern)), f"{script_path} did not produce {pattern}"


@pytest.mark.parametrize(
    "script_path",
    sorted((EXAMPLES / "customizing_generation").glob("*/demo.py")),
    ids=lambda path: path.parent.name,
)
def test_customization_demo_runs(script_path: pathlib.Path) -> None:
    runpy.run_path(str(script_path), run_name="__main__")
