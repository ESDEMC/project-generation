from qtpy.QtCore import QSettings

from project_generation_gui.preferences import (
    ApplicationPreferences,
    EditorPreferences,
    THEME_DARK,
    THEME_LIGHT,
    THEME_SYSTEM,
    install_application_style,
)


def test_editor_preferences_persist_theme_and_font_size(qtbot, tmp_path) -> None:
    settings = QSettings(str(tmp_path / "preferences.ini"), QSettings.IniFormat)
    settings.clear()
    preferences = EditorPreferences(settings=settings)

    preferences.set_font_size(15)
    preferences.set_theme(THEME_DARK)

    restored = EditorPreferences(settings=settings)
    assert restored.font_size == 15
    assert restored.theme == THEME_DARK

    restored.set_theme(THEME_LIGHT)
    restored.set_theme(THEME_SYSTEM)
    assert restored.theme == THEME_SYSTEM


def test_system_theme_always_uses_fusion_style(qtbot, tmp_path) -> None:
    from qtpy.QtWidgets import QApplication

    settings = QSettings(str(tmp_path / "system-fusion.ini"), QSettings.IniFormat)
    settings.setValue("editor/theme", THEME_SYSTEM)
    preferences = EditorPreferences(settings=settings)

    install_application_style()
    preferences.apply_theme()

    assert QApplication.instance().style().objectName().lower() == "fusion"


def test_system_theme_uses_current_style_palette(qtbot, tmp_path) -> None:
    from qtpy.QtGui import QColor, QPalette
    from qtpy.QtWidgets import QApplication

    settings = QSettings(str(tmp_path / "system-theme.ini"), QSettings.IniFormat)
    settings.setValue("editor/theme", THEME_SYSTEM)
    preferences = EditorPreferences(settings=settings)

    app = QApplication.instance()
    stale_palette = QPalette(app.palette())
    stale_palette.setColor(QPalette.Window, QColor(1, 2, 3))
    app.setPalette(stale_palette)

    preferences.apply_theme()

    expected = QApplication.style().standardPalette()
    assert app.palette().color(QPalette.Window) == expected.color(QPalette.Window)


def test_system_color_scheme_change_reapplies_system_theme(qtbot, tmp_path, monkeypatch) -> None:
    settings = QSettings(str(tmp_path / "system-theme-change.ini"), QSettings.IniFormat)
    settings.setValue("editor/theme", THEME_SYSTEM)
    preferences = EditorPreferences(settings=settings)

    applied = []
    monkeypatch.setattr(preferences, "apply_theme", lambda: applied.append(True))

    preferences._system_color_scheme_changed()

    assert applied == [True]


def test_light_theme_does_not_follow_dark_system_palette(qtbot, tmp_path) -> None:
    from qtpy.QtGui import QColor, QPalette
    from qtpy.QtWidgets import QApplication

    settings = QSettings(str(tmp_path / "light-theme.ini"), QSettings.IniFormat)
    settings.setValue("editor/theme", THEME_LIGHT)
    preferences = EditorPreferences(settings=settings)

    app = QApplication.instance()
    simulated_dark_system_palette = QPalette()
    simulated_dark_system_palette.setColor(QPalette.Window, QColor(20, 20, 20))
    simulated_dark_system_palette.setColor(QPalette.Base, QColor(10, 10, 10))
    simulated_dark_system_palette.setColor(QPalette.Text, QColor(240, 240, 240))
    app.setPalette(simulated_dark_system_palette)

    preferences.apply_theme()

    palette = app.palette()
    assert palette.color(QPalette.Window) == QColor(240, 240, 240)
    assert palette.color(QPalette.Base) == QColor(255, 255, 255)
    assert palette.color(QPalette.Text) == QColor(0, 0, 0)


def test_dark_theme_starts_from_fresh_fusion_palette(qtbot, tmp_path) -> None:
    from qtpy.QtGui import QColor, QPalette
    from qtpy.QtWidgets import QApplication

    settings = QSettings(str(tmp_path / "dark-theme.ini"), QSettings.IniFormat)
    settings.setValue("editor/theme", THEME_DARK)
    preferences = EditorPreferences(settings=settings)

    app = QApplication.instance()
    install_application_style()

    dirty_palette = QPalette(app.palette())
    dirty_palette.setColor(QPalette.Link, QColor(1, 2, 3))
    app.setPalette(dirty_palette)

    expected_link = app.style().standardPalette().color(QPalette.Link)
    preferences.apply_theme()

    palette = app.palette()
    assert palette.color(QPalette.Link) == expected_link
    assert palette.color(QPalette.Window) == QColor(45, 45, 45)
    assert palette.color(QPalette.Base) == QColor(30, 30, 30)
    assert palette.color(QPalette.Text) == QColor(230, 230, 230)


def test_application_preferences_persist_open_exported_folder(qtbot, tmp_path) -> None:
    settings = QSettings(str(tmp_path / "application-preferences.ini"), QSettings.IniFormat)
    settings.clear()
    preferences = ApplicationPreferences(settings=settings)

    assert preferences.open_folder_after_export is True

    preferences.set_open_folder_after_export(False)

    restored = ApplicationPreferences(settings=settings)
    assert restored.open_folder_after_export is False


def test_application_preferences_persist_default_export_path_and_session_restore(qtbot, tmp_path) -> None:
    settings = QSettings(str(tmp_path / "session-preferences.ini"), QSettings.IniFormat)
    settings.clear()
    preferences = ApplicationPreferences(settings=settings)
    export_path = tmp_path / "exports"

    preferences.set_default_export_path(export_path)
    preferences.set_restore_last_session(False)

    restored = ApplicationPreferences(settings=settings)
    assert restored.default_export_path == export_path
    assert restored.restore_last_session is False
