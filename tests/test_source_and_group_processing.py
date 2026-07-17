import json
from pathlib import Path

import pytest

from project_generation import (
    ProjectGenerationError,
    ProjectGenerationProcessor,
    apply_record_mapping,
    load_project_definition,
    process_project_definition,
    select_json_records,
)

ROOT = Path(__file__).parents[1]
EXAMPLES = ROOT / "examples"


def test_minimal_explicit_project_compiles_pins_and_groups() -> None:
    generated = process_project_definition(EXAMPLES / "minimal-explicit.json")

    assert [pin.designator for pin in generated.pins] == ["1", "2", "3"]
    assert [group.name for group in generated.groups] == ["SU5V5", "IN5V5", "GND"]
    assert generated.groups[1].pin_ids == (generated.pins[1].id,)


def test_pin_ids_are_deterministic() -> None:
    definition = load_project_definition(EXAMPLES / "minimal-explicit.json")
    processor = ProjectGenerationProcessor()

    first = processor.process(definition, base_directory=EXAMPLES)
    second = processor.process(definition, base_directory=EXAMPLES)

    assert [pin.id for pin in first.pins] == [pin.id for pin in second.pins]
    assert [group.id for group in first.groups] == [group.id for group in second.groups]


def test_customer_source_mapping_and_group_generation() -> None:
    generated = process_project_definition(EXAMPLES / "customer-current.json")

    assert len(generated.pins) == 5
    assert [(group.name, group.group_type, len(group.pin_ids)) for group in generated.groups] == [
        ("SU5V5", "POWER", 1),
        ("IN5V5", "INPUT", 2),
        ("O3V3", "OUTPUT", 1),
    ]
    assert generated.groups[1].parameters == {"v_max": 5.5, "v_min": 0.0}


def test_external_groups_are_left_unresolved() -> None:
    definition = load_project_definition(EXAMPLES / "six-fixed-plans.json")
    generated = ProjectGenerationProcessor().process(definition, base_directory=EXAMPLES)

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
    data = json.loads((EXAMPLES / "minimal-explicit.json").read_text())
    data["groups"]["explicit"][0]["pins"] = ["99"]
    path = tmp_path / "generation.json"
    path.write_text(json.dumps(data))

    with pytest.raises(ProjectGenerationError, match="unknown pin designators"):
        process_project_definition(path)
