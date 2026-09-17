import json
from pathlib import Path

from project_generation_gui.session import ProjectSession
from tests.support.paths import JSON_PIN_SOURCE


EXAMPLE = JSON_PIN_SOURCE.parent


def test_regeneration_uses_unsaved_source_text_without_modifying_disk(tmp_path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    generation_path = project / "generation.json"
    source_path = project / "data" / "customer-device.json"
    source_path.parent.mkdir()
    generation_path.write_text((EXAMPLE / "generation.json").read_text(encoding="utf-8"), encoding="utf-8")
    original_source = (EXAMPLE / "data" / "customer-device.json").read_text(encoding="utf-8")
    source_path.write_text(original_source, encoding="utf-8")

    session = ProjectSession()
    session.open_definition(generation_path)
    assert session.snapshot is not None
    assert session.snapshot.pins[1].name == "IN_A"

    payload = json.loads(original_source)
    payload["pins"][1]["signal_name"] = "IN_A_EDITED"
    session.update_document(source_path, json.dumps(payload, indent=2))
    session.regenerate()

    assert session.snapshot is not None
    assert session.snapshot.pins[1].name == "IN_A_EDITED"
    assert source_path.read_text(encoding="utf-8") == original_source


def test_realis_input_binding_uses_unsaved_working_copy_without_saving(tmp_path: Path) -> None:
    import shutil

    from tests.support.paths import REALIS

    definition_path = tmp_path / "generation.yaml"
    hardware_path = tmp_path / "hardware.yaml"
    input_path = tmp_path / "device.json"
    pin_map_path = tmp_path / "adapter-board.csv"
    shutil.copy(REALIS / "generation.yaml", definition_path)
    shutil.copy(REALIS / "hardware.yaml", hardware_path)
    shutil.copy(REALIS / "adapter-board.csv", pin_map_path)

    source_input = next((REALIS / "input").glob("*.json"))
    shutil.copy(source_input, input_path)

    session = ProjectSession()
    session.open_definition(definition_path)

    assert session.input_directives() == ("input_file", "adapter_board")
    assert not any(diagnostic.code == "INPUT_FILE_NOT_SET" for diagnostic in session.diagnostics)
    assert session.snapshot is None

    session.regenerate()
    assert any(diagnostic.code == "INPUT_FILE_NOT_SET" for diagnostic in session.diagnostics)

    session.set_input_file("input_file", input_path)
    assert session.snapshot is not None
    session.set_input_file("adapter_board", pin_map_path)
    assert session.snapshot is not None

    original_bytes = input_path.read_bytes()
    document = session.documents.get(input_path)
    assert document is not None
    session.update_document(input_path, document.text.replace('"ProjectName":', '"ProjectName":'))
    session.regenerate()

    assert input_path.read_bytes() == original_bytes


def test_quiet_regeneration_waits_for_required_inputs_without_reporting_an_error(tmp_path: Path) -> None:
    import shutil

    from tests.support.paths import REALIS

    definition_path = tmp_path / "generation.yaml"
    hardware_path = tmp_path / "hardware.yaml"
    input_path = tmp_path / "device.json"
    pin_map_path = tmp_path / "adapter-board.csv"
    shutil.copy(REALIS / "generation.yaml", definition_path)
    shutil.copy(REALIS / "hardware.yaml", hardware_path)
    shutil.copy(REALIS / "adapter-board.csv", pin_map_path)
    shutil.copy(next((REALIS / "input").glob("*.json")), input_path)

    session = ProjectSession()
    session.open_definition(definition_path)

    assert session.snapshot is None
    assert not any(diagnostic.code == "INPUT_FILE_NOT_SET" for diagnostic in session.diagnostics)

    session.regenerate(report_missing_inputs=False)
    assert session.snapshot is None
    assert not any(diagnostic.code == "INPUT_FILE_NOT_SET" for diagnostic in session.diagnostics)

    session.set_input_file("input_file", input_path)
    assert session.snapshot is not None
    session.set_input_file("adapter_board", pin_map_path)
    assert session.snapshot is not None


def test_definition_syntax_error_precedes_schema_validation(tmp_path) -> None:
    path = tmp_path / "generation.yaml"
    path.write_text("schema_version: '1.0'\nsources: [\n", encoding="utf-8")

    session = ProjectSession()
    session.open_definition(path)

    assert session.definition is None
    assert session.snapshot is None
    assert len(session.diagnostics) == 1
    assert session.diagnostics[0].code == "SYNTAX_ERROR"
    assert session.diagnostics[0].location.startswith("generation.yaml:")


def test_valid_syntax_is_schema_validated_after_parsing(tmp_path) -> None:
    path = tmp_path / "generation.json"
    path.write_text("{}", encoding="utf-8")

    session = ProjectSession()
    session.open_definition(path)

    assert session.snapshot is None
    assert len(session.diagnostics) == 1
    assert session.diagnostics[0].code == "SCHEMA_VALIDATION_ERROR"


def test_referenced_json_syntax_is_checked_before_generation(tmp_path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    generation_path = project / "generation.json"
    source_path = project / "data" / "customer-device.json"
    source_path.parent.mkdir()
    generation_path.write_text((EXAMPLE / "generation.json").read_text(encoding="utf-8"), encoding="utf-8")
    source_path.write_text((EXAMPLE / "data" / "customer-device.json").read_text(encoding="utf-8"), encoding="utf-8")

    session = ProjectSession()
    session.open_definition(generation_path)
    previous_snapshot = session.snapshot
    assert previous_snapshot is not None

    session.update_document(source_path, '{"pins": [')
    session.regenerate()

    assert session.snapshot is previous_snapshot
    assert len(session.diagnostics) == 1
    assert session.diagnostics[0].code == "SYNTAX_ERROR"
    assert session.diagnostics[0].location.startswith("customer-device.json:")


def test_clear_diagnostics_clears_until_next_regeneration(tmp_path) -> None:
    definition_path = tmp_path / "generation.yaml"
    definition_path.write_text("sources: []", encoding="utf-8")

    session = ProjectSession()
    session.open_definition(definition_path)
    assert session.diagnostics

    session.clear_diagnostics()
    assert session.diagnostics == ()

    session.regenerate()
    assert session.diagnostics


def test_session_keeps_partial_snapshot_when_group_generation_fails(tmp_path: Path) -> None:
    definition_path = tmp_path / "generation.json"
    definition_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "project": {"name": "partial"},
                "dut": {
                    "name": "DUT",
                    "pins": {
                        "source": {
                            "type": "inline",
                            "records": [
                                {"designator": "1", "name": "A"},
                                {"designator": "2", "name": "B"},
                            ],
                        }
                    },
                },
                "groups": {
                    "explicit": [
                        {"name": "GOOD", "group_type": "INPUT", "pins": ["1"]},
                        {"name": "BAD", "group_type": "OUTPUT", "pins": ["99"]},
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    session = ProjectSession()
    session.open_definition(definition_path)

    assert session.snapshot is not None
    assert [pin.designator for pin in session.snapshot.pins] == ["1", "2"]
    assert [group.name for group in session.snapshot.groups] == ["GOOD"]
    assert session.snapshot.stage("groups").status.value == "failed"
    assert any(diagnostic.code == "group.unknown_pins" for diagnostic in session.diagnostics)


def test_rebinding_input_does_not_make_old_input_a_referenced_file(tmp_path: Path) -> None:
    import shutil

    from tests.support.paths import REALIS

    definition_path = tmp_path / "generation.yaml"
    hardware_path = tmp_path / "hardware.yaml"
    first_input = tmp_path / "first.json"
    second_input = tmp_path / "second.json"
    shutil.copy(REALIS / "generation.yaml", definition_path)
    shutil.copy(REALIS / "hardware.yaml", hardware_path)
    source_input = next((REALIS / "input").glob("*.json"))
    shutil.copy(source_input, first_input)
    shutil.copy(source_input, second_input)

    session = ProjectSession()
    session.open_definition(definition_path)
    session.set_input_file("input_file", first_input)
    session.set_input_file("input_file", second_input)

    assert session.input_bindings["input_file"] == second_input.resolve()
    assert first_input.resolve() not in {document.path for document in session.active_documents()}
    assert first_input.resolve() not in {document.path for document in session.referenced_documents()}
    assert second_input.resolve() in {document.path for document in session.active_documents()}
