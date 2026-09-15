import sys
from pathlib import Path

from qtpy.QtWidgets import QApplication

from project_generation_gui.main_window import MainWindow


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    window = MainWindow()
    if len(sys.argv) > 1:
        window.open_definition(Path(sys.argv[1]))
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
