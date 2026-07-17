import json

from project_generation import (
    ProjectGenerationDefinition,
    ProjectGenerationProcessor,
    generated_project_to_dict,
    generated_project_to_json,
    write_generated_project,
)


def _project():
    definition = ProjectGenerationDefinition.model_validate(
        {
            "schema_version": "1.0",
            "project": {"name": "Serializable"},
            "groups": {"external": True},
            "power_resources": {"DC2": {"role": "BIAS"}},
            "device_states": {
                "active": {
                    "power_domains": [
                        {
                            "name": "supply",
                            "groups": ["SUPPLY"],
                            "assignment": "DC2",
                            "bias": {"mode": "VOLTAGE", "level": 5.0},
                        }
                    ]
                }
            },
        }
    )
    return ProjectGenerationProcessor().process(definition)


def test_generated_project_serializes_to_neutral_json_values() -> None:
    data = generated_project_to_dict(_project())

    assert data["name"] == "Serializable"
    assert data["device_states"][0]["power_on_sequence"][0]["domain_name"] == "supply"
    assert data["device_states"][0]["power_off_sequence"][0]["domain_name"] == "supply"
    json.dumps(data)


def test_generated_project_json_is_deterministic() -> None:
    project = _project()
    assert generated_project_to_json(project) == generated_project_to_json(project)


def test_generated_project_can_be_written(tmp_path) -> None:
    path = tmp_path / "generated-project.json"
    write_generated_project(_project(), path)

    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["name"] == "Serializable"
