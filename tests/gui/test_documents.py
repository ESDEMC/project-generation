from project_generation_gui.documents import DocumentManager


def test_document_changes_do_not_touch_disk_until_save(tmp_path) -> None:
    path = tmp_path / "generation.yaml"
    path.write_text("a: 1\n", encoding="utf-8")
    manager = DocumentManager()
    document = manager.open(path)

    document.text = "a: 2\n"

    assert document.dirty
    assert path.read_text(encoding="utf-8") == "a: 1\n"

    document.save()

    assert path.read_text(encoding="utf-8") == "a: 2\n"
