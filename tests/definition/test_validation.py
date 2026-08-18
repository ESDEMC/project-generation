from project_generation.definition.models import ProjectGenerationDefinition
from project_generation.definition.validation import validate_project_definition


def test_missing_device_state_is_reported() -> None:
    definition = ProjectGenerationDefinition.model_validate(
        {
            "schema_version": "1.0",
            "project": {"name": "invalid"},
            "groups": {"external": True},
            "test_plan_generation": {
                "rules": [
                    {
                        "id": "rule",
                        "groups": {"partition": {"mode": "all"}},
                        "dimensions": [
                            {"name": "mode", "values": [{"value": "A", "set": {"device_state": "missing"}}]}
                        ],
                        "template": {"test_type": "SIGNAL"},
                    }
                ]
            },
        }
    )
    diagnostics = validate_project_definition(definition)
    assert diagnostics.has_errors
    assert any(item.code == "DEVICE_STATE_NOT_FOUND" for item in diagnostics)
