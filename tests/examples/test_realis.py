import importlib.util
import pathlib

from tests.support.paths import REALIS

EXAMPLE = REALIS / "generate_projects.py"
INPUT = REALIS / "input"


def load_example_module():
    spec = importlib.util.spec_from_file_location("generate_realis_projects", EXAMPLE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_realis_example_generates_project_packages(tmp_path: pathlib.Path) -> None:
    module = load_example_module()
    input_paths = sorted(INPUT.glob("*.json"))

    assert input_paths

    for input_path in input_paths:
        project_path = module.generate_realis_project(module.DEFAULT_DEFINITION_PATH, input_path, tmp_path)
        assert project_path.exists()
        assert project_path.suffix == ".Prj"
        assert list(project_path.parent.glob("*.LuDut"))
        assert list((project_path.parent / "Testing").glob("*.LuTstPlan"))
