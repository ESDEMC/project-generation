import pathlib
import runpy

import pytest

ROOT = pathlib.Path(__file__).parents[1]
EXAMPLES = ROOT / "examples"
EXAMPLE_SCRIPTS = sorted(
    path
    for path in EXAMPLES.rglob("*.py")
    if "__pycache__" not in path.parts
)


@pytest.mark.parametrize("path", EXAMPLE_SCRIPTS, ids=lambda path: str(path.relative_to(EXAMPLES)).replace("/", "-"))
def test_python_example_runs(path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PROJECT_GENERATION_OUTPUT_DIRECTORY", str(tmp_path / "generated"))
    runpy.run_path(str(path), run_name="__main__")


def test_generation_scripts_keep_definitions_in_the_same_directory() -> None:
    generation_scripts = [path for path in EXAMPLE_SCRIPTS if path.name.startswith(("generate_", "validate_", "inspect_"))]

    for script_path in generation_scripts:
        local_definitions = list(script_path.parent.glob("generation.json")) + list(script_path.parent.glob("generation.yaml"))
        local_definitions += list(script_path.parent.glob("*-generation.json"))
        assert local_definitions, f"{script_path} does not have a co-located generation definition"
