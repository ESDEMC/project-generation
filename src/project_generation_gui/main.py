import sys
from pathlib import Path

from qtpy.QtWidgets import QApplication

from project_generation_gui.preferences import EditorPreferences, install_application_style


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)

    install_application_style()
    editor_preferences = EditorPreferences()
    editor_preferences.apply_theme()

    from project_generation_gui.main_window import MainWindow

    window = MainWindow(editor_preferences=editor_preferences)
    if len(sys.argv) > 1:
        window.open_definition(Path(sys.argv[1]))
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
