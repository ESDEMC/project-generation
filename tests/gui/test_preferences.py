from qtpy.QtCore import QSettings

from project_generation_gui.preferences import EditorPreferences, THEME_DARK, THEME_LIGHT, THEME_SYSTEM


def test_editor_preferences_persist_theme_and_font_size(qtbot, tmp_path) -> None:
    settings = QSettings(str(tmp_path / "preferences.ini"), QSettings.IniFormat)
    settings.clear()
    preferences = EditorPreferences(settings=settings)

    preferences.set_font_size(15)
    preferences.set_theme(THEME_DARK)

    restored = EditorPreferences(settings=settings)
    assert restored.font_size == 15
    assert restored.theme == THEME_DARK

    # All three supported values remain accepted settings choices.
    restored.set_theme(THEME_LIGHT)
    restored.set_theme(THEME_SYSTEM)
    assert restored.theme == THEME_SYSTEM
