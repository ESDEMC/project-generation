import json

from jsonschema import Draft202012Validator

from project_generation.models import ProjectGenerationDefinition
from conftest import EXAMPLES


def test_generated_schema_accepts_examples() -> None:
    validator = Draft202012Validator(ProjectGenerationDefinition.model_json_schema())
    paths = list(EXAMPLES.glob("*.json"))

    assert paths, f"no examples found in {EXAMPLES}"

    for path in paths:
        errors = list(validator.iter_errors(json.loads(path.read_text(encoding="utf-8"))))
        assert not errors, f"{path}: {[error.message for error in errors]}"
