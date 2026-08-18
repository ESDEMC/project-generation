from tests.support.paths import EXPLICIT_PROJECT, EXAMPLES, GROUP_GENERATION, JSON_PIN_SOURCE
import json
from pathlib import Path

import pytest

from project_generation import (
    ProjectGenerationDefinition,
    ProjectGenerationError,
    ProjectGenerationProcessor,
    load_project_definition,
    process_project_definition,
)
from project_generation.generation.processor import (
    apply_record_mapping,
    select_json_records,
)



def test_minimal_explicit_project_compiles_pins_and_groups() -> None:
    generated = process_project_definition(EXPLICIT_PROJECT)

    assert [pin.designator for pin in generated.pins] == ["1", "2", "3"]
    assert [group.name for group in generated.groups] == ["SU5V5", "IN5V5", "GND"]
    assert generated.groups[1].pin_ids == (generated.pins[1].id,)


def test_pin_ids_are_deterministic() -> None:
    definition = load_project_definition(EXPLICIT_PROJECT)
    processor = ProjectGenerationProcessor()

    first = processor.process(definition, base_directory=EXAMPLES)
    second = processor.process(definition, base_directory=EXAMPLES)

    assert [pin.id for pin in first.pins] == [pin.id for pin in second.pins]
    assert [group.id for group in first.groups] == [group.id for group in second.groups]


def test_json_source_mapping() -> None:
    generated = process_project_definition(JSON_PIN_SOURCE)

    assert len(generated.pins) == 5
    assert [pin.designator for pin in generated.pins] == ["1", "2", "3", "4", "5"]
    assert generated.pins[1].name == "IN_A"
    assert generated.pins[1].parameters["pin_type"] == "INPUT"


def test_generated_groups() -> None:
    generated = process_project_definition(GROUP_GENERATION)

    assert [(group.name, group.group_type, len(group.pin_ids)) for group in generated.groups] == [
        ("GND", "GROUND", 1),
        ("SU5V5", "POWER", 1),
        ("IN5V5", "INPUT", 2),
        ("OUT3V3", "OUTPUT", 1),
    ]
    assert generated.groups[2].parameters == {"v_max": 5.5, "v_min": 0.0}


def test_external_groups_are_left_unresolved() -> None:
    definition = ProjectGenerationDefinition.model_validate(
        {
            "schema_version": "1.0",
            "project": {"name": "External groups"},
            "groups": {"external": True},
        }
    )
    generated = ProjectGenerationProcessor().process(definition)

    assert generated.groups == ()


def test_record_mapping_builds_nested_targets() -> None:
    mapped = apply_record_mapping(
        {"pin": "7", "type": "INPUT", "maximum": 5.5},
        {
            "designator": "pin",
            "parameters.pin_type": "type",
            "parameters.v_max": "maximum",
        },
    )

    assert mapped == {"designator": "7", "parameters": {"pin_type": "INPUT", "v_max": 5.5}}


def test_simple_json_selector() -> None:
    assert select_json_records({"device": {"pins": [{"pin": 1}, {"pin": 2}]}}, "$.device.pins[*]") == [
        {"pin": 1},
        {"pin": 2},
    ]


def test_unknown_explicit_pin_is_rejected(tmp_path: Path) -> None:
    data = json.loads((EXPLICIT_PROJECT).read_text())
    data["groups"]["explicit"][0]["pins"] = ["99"]
    path = tmp_path / "generation.json"
    path.write_text(json.dumps(data))

    with pytest.raises(ProjectGenerationError, match="unknown pin designators"):
        process_project_definition(path)
