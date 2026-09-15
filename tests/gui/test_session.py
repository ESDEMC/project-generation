import json
from pathlib import Path

from project_generation_gui.session import ProjectSession


EXAMPLE = Path("examples/sources/json_pin_source")


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
