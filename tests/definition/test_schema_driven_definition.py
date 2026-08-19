from project_generation.definition.models import ProjectGenerationDefinition
from project_generation.generation.processor import ProjectGenerationProcessor


def test_conditional_group_values_and_name_fields() -> None:
    definition = ProjectGenerationDefinition.model_validate(
        {
            "schema_version": "1.0",
            "project": {"name": "test"},
            "mappings": {"prefix": {"POWER": "Su", "INPUT": "In"}},
            "formatters": {"voltage": {"type": "decimal_token", "separator": "V", "decimal_places": 1}},
            "dut": {
                "name": "DUT",
                "pins": {
                    "source": {
                        "type": "inline",
                        "records": [
                            {"designator": "1", "name": "VDD", "parameters": {"pin_type": "POWER", "v_max": "5.0"}},
                            {"designator": "2", "name": "IN", "parameters": {"pin_type": "INPUT", "v_max": "3.3"}},
                        ],
                    }
                },
            },
            "groups": {
                "generation": [
                    {
                        "id": "groups",
                        "group_by": ["parameters.pin_type", "parameters.v_max"],
                        "set": {
                            "group_type": {"from": "partition.parameters.pin_type"},
                            "parameters.v_max": {"from": "partition.parameters.v_max", "cast": "float"},
                            "parameters.compliance_limit": [
                                {"when": {"partition.parameters.pin_type": "POWER"}, "value": 0.2},
                                {
                                    "when": {"partition.parameters.pin_type": {"in": ["INPUT", "IO", "OUTPUT"]}},
                                    "value": 0.12,
                                },
                            ],
                        },
                        "name": {
                            "template": "{prefix}{voltage}",
                            "fields": {
                                "prefix": {"source": "partition.parameters.pin_type", "mapping": "prefix"},
                                "voltage": {
                                    "source": "partition.parameters.v_max",
                                    "formatter": "voltage",
                                    "when": {"partition.parameters.pin_type": {"in": ["INPUT", "IO", "OUTPUT"]}},
                                },
                            },
                        },
                    }
                ]
            },
        }
    )

    project = ProjectGenerationProcessor().process(definition)
    groups = {group.group_type: group for group in project.groups}

    assert groups["POWER"].name == "Su"
    assert groups["POWER"].parameters["compliance_limit"] == 0.2
    assert groups["INPUT"].name == "In3V3"
    assert groups["INPUT"].parameters["compliance_limit"] == 0.12


def test_definition_defaults_remain_usable() -> None:
    definition = ProjectGenerationDefinition.model_validate(
        {
            "schema_version": "1.0",
            "project": {"name": "defaults"},
        }
    )

    project = ProjectGenerationProcessor().process(definition)

    assert project.name == "defaults"
    assert project.groups == ()
    assert project.device_states == ()
    assert project.test_plans == ()
