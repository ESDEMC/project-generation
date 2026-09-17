from pathlib import Path

from project_generation.definition.models import ProjectGenerationDefinition
from project_generation.generation.processor import ProjectGenerationProcessor


def test_pin_map_supports_direct_device_to_tester_locations(tmp_path: Path) -> None:
    definition = ProjectGenerationDefinition.model_validate(
        {
            "schema_version": "1.0",
            "project": {"name": "Direct"},
            "dut": {
                "name": "DUT",
                "pins": {
                    "source": {
                        "type": "inline",
                        "records": [
                            {"designator": "1", "name": "A", "parameters": {"tester_location": "T12"}},
                            {"designator": "2", "name": "B", "parameters": {"tester_location": "T13"}},
                        ],
                    }
                },
            },
            "pin_map": {"location": "parameters.tester_location"},
        }
    )

    project = ProjectGenerationProcessor().process(definition, base_directory=tmp_path)

    assert [(entry.pin, entry.location) for entry in project.pin_map] == [("1", "T12"), ("2", "T13")]


def test_pin_map_can_map_socket_locations_through_an_input_source(tmp_path: Path) -> None:
    mapping_path = tmp_path / "tester.csv"
    mapping_path.write_text("Socket,Location\nA1,T12\nA2,T13\n", encoding="utf-8")
    definition = ProjectGenerationDefinition.model_validate(
        {
            "schema_version": "1.0",
            "project": {"name": "Socketed"},
            "sources": {
                "tester_map": {
                    "type": "csv",
                    "path": str(mapping_path),
                    "mapping": {"socket": "Socket", "location": "Location"},
                }
            },
            "dut": {
                "name": "DUT",
                "pins": {
                    "source": {
                        "type": "inline",
                        "records": [
                            {"designator": "1", "name": "A", "parameters": {"socket": "A1"}},
                            {"designator": "2", "name": "B", "parameters": {"socket": "A2"}},
                        ],
                    }
                },
            },
            "pin_map": {
                "location": "parameters.socket",
                "mappings": [{"source": "tester_map", "from": "socket", "to": "location"}],
            },
        }
    )

    project = ProjectGenerationProcessor().process(definition, base_directory=tmp_path)

    assert [(entry.pin, entry.location) for entry in project.pin_map] == [("1", "T12"), ("2", "T13")]


def test_pin_map_uses_identity_when_optional_mapping_input_is_unbound(tmp_path: Path) -> None:
    definition = ProjectGenerationDefinition.model_validate(
        {
            "schema_version": "1.0",
            "project": {"name": "Identity"},
            "sources": {
                "adapter_board": {
                    "type": "csv",
                    "path": "{adapter_board}",
                    "mapping": {"socket": "Socket", "location": "Location"},
                }
            },
            "dut": {
                "name": "DUT",
                "pins": {
                    "source": {
                        "type": "inline",
                        "records": [
                            {"designator": "1", "name": "A", "parameters": {"socket": "A1"}},
                            {"designator": "2", "name": "B", "parameters": {"socket": "A2"}},
                        ],
                    }
                },
            },
            "pin_map": {
                "location": "parameters.socket",
                "mappings": [
                    {
                        "source": "adapter_board",
                        "from": "socket",
                        "to": "location",
                        "on_missing": "identity",
                    }
                ],
            },
        }
    )

    project = ProjectGenerationProcessor().process(definition, base_directory=tmp_path)

    assert [(entry.pin, entry.location) for entry in project.pin_map] == [("1", "A1"), ("2", "A2")]
