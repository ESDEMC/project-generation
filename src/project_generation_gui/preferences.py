from qtpy.QtCore import QObject, QSettings, Signal
from qtpy.QtGui import QColor, QPalette
from qtpy.QtWidgets import QApplication, QStyleFactory


THEME_SYSTEM = "System"
THEME_LIGHT = "Light"
THEME_DARK = "Dark"
THEMES = (THEME_SYSTEM, THEME_LIGHT, THEME_DARK)


class EditorPreferences(QObject):
    changed = Signal()

    def __init__(self, parent: QObject | None = None, *, settings: QSettings | None = None) -> None:
        super().__init__(parent)
        self._settings = settings or QSettings("project-generation", "project-generation-gui")
        self._theme = str(self._settings.value("editor/theme", THEME_SYSTEM))
        if self._theme not in THEMES:
            self._theme = THEME_SYSTEM
        self._font_size = int(self._settings.value("editor/font_size", 10))

        app = QApplication.instance()
        self._system_style_name = app.style().objectName() if app is not None else ""
        self._system_palette = QPalette(app.palette()) if app is not None else QPalette()

    @property
    def theme(self) -> str:
        return self._theme

    @property
    def font_size(self) -> int:
        return self._font_size

    def set_theme(self, theme: str) -> None:
        if theme not in THEMES:
            raise ValueError(f"Unknown theme: {theme}")
        if theme == self._theme:
            return
        self._theme = theme
        self._settings.setValue("editor/theme", theme)
        self.apply_theme()
        self.changed.emit()

    def set_font_size(self, size: int) -> None:
        size = max(6, min(48, int(size)))
        if size == self._font_size:
            return
        self._font_size = size
        self._settings.setValue("editor/font_size", size)
        self.changed.emit()

    def apply_theme(self) -> None:
        app = QApplication.instance()
        if app is None:
            return

        if self._theme == THEME_SYSTEM:
            if self._system_style_name:
                QApplication.setStyle(self._system_style_name)
            app.setPalette(self._system_palette)
            return

        fusion = QStyleFactory.create("Fusion")
        if fusion is not None:
            QApplication.setStyle(fusion)

        if self._theme == THEME_LIGHT:
            app.setPalette(QApplication.style().standardPalette())
        else:
            app.setPalette(_dark_palette())


def _dark_palette() -> QPalette:
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(45, 45, 45))
    palette.setColor(QPalette.WindowText, QColor(230, 230, 230))
    palette.setColor(QPalette.Base, QColor(30, 30, 30))
    palette.setColor(QPalette.AlternateBase, QColor(45, 45, 45))
    palette.setColor(QPalette.ToolTipBase, QColor(230, 230, 230))
    palette.setColor(QPalette.ToolTipText, QColor(30, 30, 30))
    palette.setColor(QPalette.Text, QColor(230, 230, 230))
    palette.setColor(QPalette.Button, QColor(45, 45, 45))
    palette.setColor(QPalette.ButtonText, QColor(230, 230, 230))
    palette.setColor(QPalette.BrightText, QColor(255, 80, 80))
    palette.setColor(QPalette.Highlight, QColor(42, 130, 218))
    palette.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
    palette.setColor(QPalette.PlaceholderText, QColor(150, 150, 150))
    palette.setColor(QPalette.Disabled, QPalette.Text, QColor(120, 120, 120))
    palette.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(120, 120, 120))
    return palette
