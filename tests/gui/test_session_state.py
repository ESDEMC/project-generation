from qtpy.QtCore import QByteArray, QSettings

from project_generation_gui.session_state import SessionState, SessionStore


def test_session_store_round_trip(tmp_path) -> None:
    settings = QSettings(str(tmp_path / "sessions.ini"), QSettings.IniFormat)
    store = SessionStore(settings)
    definition = tmp_path / "generation.yaml"
    definition.write_text("{}", encoding="utf-8")
    input_file = tmp_path / "pins.csv"
    input_file.write_text("pin", encoding="utf-8")
    state = SessionState(
        definition_path=str(definition),
        input_bindings=(("pin_file", str(input_file)),),
        open_documents=(str(definition), str(input_file)),
        generated_views=("Pins", "Groups"),
        dirty_documents=((str(definition), "changed"),),
        current_document=str(input_file),
        export_directory=str(tmp_path / "export"),
    )
    central_state = QByteArray(b"dock-state")

    store.save(state, central_state)

    restored = store.last()
    assert restored is not None
    assert restored.definition_path == str(definition.resolve())
    assert restored.input_bindings == state.input_bindings
    assert restored.open_documents == state.open_documents
    assert restored.generated_views == state.generated_views
    assert restored.dirty_documents == state.dirty_documents
    assert restored.current_document == state.current_document
    assert restored.export_directory == state.export_directory
    assert store.central_state(definition) == central_state
