import json

from jsonschema import Draft202012Validator

from project_generation.definition.models import ProjectGenerationDefinition
from tests.support.paths import EXAMPLES


def test_generated_schema_accepts_examples() -> None:
    validator = Draft202012Validator(ProjectGenerationDefinition.model_json_schema())
    paths = sorted(
        path
        for path in EXAMPLES.rglob("*.json")
        if path.name == "generation.json" or path.name.endswith("-generation.json")
    )

    assert paths, f"no examples found in {EXAMPLES}"

    for path in paths:
        errors = list(validator.iter_errors(json.loads(path.read_text(encoding="utf-8"))))
        assert not errors, f"{path}: {[error.message for error in errors]}"
