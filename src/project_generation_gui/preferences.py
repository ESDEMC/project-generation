from pathlib import Path

from qtpy.QtCore import QObject, QSettings, Signal
from qtpy.QtGui import QColor, QPalette
from qtpy.QtWidgets import QApplication, QStyleFactory


THEME_SYSTEM = "System"
THEME_LIGHT = "Light"
THEME_DARK = "Dark"
THEMES = (THEME_SYSTEM, THEME_LIGHT, THEME_DARK)


def install_application_style() -> None:
    """Install the single application style before any application widgets are created."""
    app = QApplication.instance()
    if app is None:
        return
    if app.style().objectName().lower() == "fusion":
        return
    fusion = QStyleFactory.create("Fusion")
    if fusion is not None:
        app.setStyle(fusion)


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
        self._style_hints = app.styleHints() if app is not None else None
        if self._style_hints is not None:
            self._style_hints.colorSchemeChanged.connect(self._system_color_scheme_changed)

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
            app.setPalette(app.style().standardPalette())
            return

        if self._theme == THEME_LIGHT:
            app.setPalette(_light_palette())
        else:
            app.setPalette(_dark_palette())

    def _system_color_scheme_changed(self, *_args) -> None:
        if self._theme == THEME_SYSTEM:
            self.apply_theme()


class ApplicationPreferences(QObject):
    changed = Signal()

    def __init__(self, parent: QObject | None = None, *, settings: QSettings | None = None) -> None:
        super().__init__(parent)
        self._settings = settings or QSettings("project-generation", "project-generation-gui")
        value = self._settings.value("export/open_folder_after_export", True)
        self._open_folder_after_export = value if isinstance(value, bool) else str(value).lower() == "true"
        default_export = self._settings.value("export/default_path", str(Path.home()))
        self._default_export_path = Path(str(default_export)).expanduser()
        restore_value = self._settings.value("sessions/restore_last", True)
        self._restore_last_session = (
            restore_value if isinstance(restore_value, bool) else str(restore_value).lower() == "true"
        )

    @property
    def settings(self) -> QSettings:
        return self._settings

    @property
    def open_folder_after_export(self) -> bool:
        return self._open_folder_after_export

    @property
    def default_export_path(self) -> Path:
        return self._default_export_path

    @property
    def restore_last_session(self) -> bool:
        return self._restore_last_session

    def set_open_folder_after_export(self, enabled: bool) -> None:
        enabled = bool(enabled)
        if enabled == self._open_folder_after_export:
            return
        self._open_folder_after_export = enabled
        self._settings.setValue("export/open_folder_after_export", enabled)
        self.changed.emit()

    def set_default_export_path(self, path: str | Path) -> None:
        text = str(path).strip()
        if not text:
            return
        resolved = Path(text).expanduser()
        if resolved == self._default_export_path:
            return
        self._default_export_path = resolved
        self._settings.setValue("export/default_path", str(resolved))
        self.changed.emit()

    def set_restore_last_session(self, enabled: bool) -> None:
        enabled = bool(enabled)
        if enabled == self._restore_last_session:
            return
        self._restore_last_session = enabled
        self._settings.setValue("sessions/restore_last", enabled)
        self.changed.emit()


def _fresh_fusion_palette() -> QPalette:
    """Return a fresh copy of the current Fusion style palette."""
    app = QApplication.instance()
    if app is None:
        return QPalette()
    return QPalette(app.style().standardPalette())


def _light_palette() -> QPalette:
    """Return a deterministic light palette using a fresh Fusion baseline."""
    palette = _fresh_fusion_palette()
    palette.setColor(QPalette.Window, QColor(240, 240, 240))
    palette.setColor(QPalette.WindowText, QColor(0, 0, 0))
    palette.setColor(QPalette.Base, QColor(255, 255, 255))
    palette.setColor(QPalette.AlternateBase, QColor(245, 245, 245))
    palette.setColor(QPalette.ToolTipBase, QColor(255, 255, 220))
    palette.setColor(QPalette.ToolTipText, QColor(0, 0, 0))
    palette.setColor(QPalette.Text, QColor(0, 0, 0))
    palette.setColor(QPalette.Button, QColor(240, 240, 240))
    palette.setColor(QPalette.ButtonText, QColor(0, 0, 0))
    palette.setColor(QPalette.BrightText, QColor(255, 0, 0))
    palette.setColor(QPalette.Light, QColor(255, 255, 255))
    palette.setColor(QPalette.Midlight, QColor(227, 227, 227))
    palette.setColor(QPalette.Dark, QColor(160, 160, 160))
    palette.setColor(QPalette.Mid, QColor(184, 184, 184))
    palette.setColor(QPalette.Shadow, QColor(105, 105, 105))
    palette.setColor(QPalette.Highlight, QColor(42, 130, 218))
    palette.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
    palette.setColor(QPalette.Link, QColor(0, 0, 255))
    palette.setColor(QPalette.LinkVisited, QColor(128, 0, 128))
    palette.setColor(QPalette.PlaceholderText, QColor(128, 128, 128))
    palette.setColor(QPalette.Disabled, QPalette.WindowText, QColor(120, 120, 120))
    palette.setColor(QPalette.Disabled, QPalette.Text, QColor(120, 120, 120))
    palette.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(120, 120, 120))
    palette.setColor(QPalette.Disabled, QPalette.HighlightedText, QColor(190, 190, 190))
    return palette


def _dark_palette() -> QPalette:
    """Return a dark palette using a fresh Fusion baseline."""
    palette = _fresh_fusion_palette()
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
