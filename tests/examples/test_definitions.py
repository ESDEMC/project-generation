import pathlib

import pytest

from project_generation import load_project_definition, validate_project_definition
from tests.support.paths import EXAMPLES

DEFINITIONS = sorted([*EXAMPLES.rglob("generation.json"), *EXAMPLES.rglob("generation.yaml")])


@pytest.mark.parametrize("path", DEFINITIONS, ids=lambda path: str(path.relative_to(EXAMPLES)))
def test_examples_load_and_validate(path: pathlib.Path) -> None:
    definition = load_project_definition(path)
    diagnostics = validate_project_definition(definition)
    assert not diagnostics.has_errors, "\n".join(item.format() for item in diagnostics)
