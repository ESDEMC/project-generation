import ast
import pathlib
import runpy
import sys

import pytest

from tests.support.paths import EXAMPLES

EXAMPLE_SCRIPTS = sorted(path for path in EXAMPLES.rglob("*.py") if "__pycache__" not in path.parts)


@pytest.mark.parametrize(
    "path", EXAMPLE_SCRIPTS, ids=lambda path: str(path.relative_to(EXAMPLES)).replace("/", "-")
)
def test_python_example_runs(path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PROJECT_GENERATION_OUTPUT_DIRECTORY", str(tmp_path / "generated"))
    monkeypatch.setattr(sys, "argv", [str(path)])
    runpy.run_path(str(path), run_name="__main__")


def test_example_scripts_have_a_definition_in_their_example_directory() -> None:
    for script_path in EXAMPLE_SCRIPTS:
        example_directory = script_path.parent
        local_definitions = list(example_directory.glob("generation.json")) + list(example_directory.glob("generation.yaml"))
        assert local_definitions, f"{script_path} does not have a generation definition in its example directory"


def test_example_scripts_have_explanatory_docstrings() -> None:
    for path in EXAMPLE_SCRIPTS:
        module = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        docstring = ast.get_docstring(module)
        assert docstring is not None and len(docstring.strip()) >= 40, f"{path} needs an explanatory module docstring"
