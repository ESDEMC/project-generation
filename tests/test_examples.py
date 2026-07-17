import pathlib

import pytest

from project_generation import load_project_definition, validate_project_definition

EXAMPLES = pathlib.Path(__file__).parents[1] / "examples"


@pytest.mark.parametrize("path", sorted(EXAMPLES.glob("*.json")), ids=lambda path: path.stem)
def test_examples_load_and_validate(path: pathlib.Path) -> None:
    definition = load_project_definition(path)
    diagnostics = validate_project_definition(definition)
    assert not diagnostics.has_errors, "\n".join(item.format() for item in diagnostics)
