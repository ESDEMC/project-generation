from dataclasses import dataclass
from hashlib import sha1
from typing import Iterable

from qtpy.QtCore import QObject, QSettings, Qt, Signal
from qtpy.QtGui import QColor

from project_generation_gui.preferences import ApplicationPreferences, EditorPreferences, THEMES
from qtpy.QtWidgets import (
    QAbstractItemView,
    QColorDialog,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QSpinBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)


TYPE_CATEGORY = "type"
ASSIGNMENT_CATEGORY = "assignment"


@dataclass(frozen=True)
class ColorPalette:
    name: str
    type_colors: dict[str, str]
    assignment_colors: dict[str, str]
    fallback_colors: tuple[str, ...]


PALETTES: dict[str, ColorPalette] = {
    "Default": ColorPalette(
        name="Default",
        type_colors={
            "INPUT": "#29B6F6",
            "OUTPUT": "#FFA726",
            "IO": "#AB47BC",
            "POWER": "#EF5350",
            "GROUND": "#66BB6A",
            "NC": "#90A4AE",
        },
        assignment_colors={
            "GROUND": "#66BB6A",
            "FLOATING": "#90A4AE",
            "DC1": "#42A5F5",
            "DC2": "#AB47BC",
            "DC3": "#FFA726",
            "DC4": "#26A69A",
        },
        fallback_colors=("#42A5F5", "#AB47BC", "#FFA726", "#26A69A", "#EC407A", "#7E57C2"),
    ),
    "Pastel": ColorPalette(
        name="Pastel",
        type_colors={
            "INPUT": "#81D4FA",
            "OUTPUT": "#FFCC80",
            "IO": "#CE93D8",
            "POWER": "#EF9A9A",
            "GROUND": "#A5D6A7",
            "NC": "#B0BEC5",
        },
        assignment_colors={
            "GROUND": "#A5D6A7",
            "FLOATING": "#B0BEC5",
            "DC1": "#90CAF9",
            "DC2": "#CE93D8",
            "DC3": "#FFCC80",
            "DC4": "#80CBC4",
        },
        fallback_colors=("#90CAF9", "#CE93D8", "#FFCC80", "#80CBC4", "#F48FB1", "#B39DDB"),
    ),
    "High Contrast": ColorPalette(
        name="High Contrast",
        type_colors={
            "INPUT": "#00BFFF",
            "OUTPUT": "#FF8C00",
            "IO": "#FF00FF",
            "POWER": "#FF3030",
            "GROUND": "#00C853",
            "NC": "#A0A0A0",
        },
        assignment_colors={
            "GROUND": "#00C853",
            "FLOATING": "#A0A0A0",
            "DC1": "#00BFFF",
            "DC2": "#FF00FF",
            "DC3": "#FF8C00",
            "DC4": "#00C9A7",
        },
        fallback_colors=("#00BFFF", "#FF00FF", "#FF8C00", "#00C9A7", "#FF4081", "#7C4DFF"),
    ),
}


class ColorTheme(QObject):
    """Persistent presentation colors for semantic generated-project values."""

    changed = Signal()

    def __init__(self, parent: QObject | None = None, *, settings: QSettings | None = None) -> None:
        super().__init__(parent)
        self._settings = settings or QSettings("project-generation", "project-generation-gui")
        self._palette_name = str(self._settings.value("colors/palette", "Default"))
        if self._palette_name not in PALETTES:
            self._palette_name = "Default"
        self._overrides: dict[tuple[str, str], str] = {}
        self._known_values: dict[str, set[str]] = {TYPE_CATEGORY: set(), ASSIGNMENT_CATEGORY: set()}
        self._custom_values: dict[str, list[str]] = {TYPE_CATEGORY: [], ASSIGNMENT_CATEGORY: []}
        self._automatic_colors: dict[tuple[str, str], str] = {}
        self._load_overrides()
        self._load_custom_values()

    @property
    def palette_name(self) -> str:
        return self._palette_name

    def set_palette(self, name: str) -> None:
        if name not in PALETTES:
            raise ValueError(f"Unknown color palette: {name}")
        if name == self._palette_name:
            return
        self._palette_name = name
        self._settings.setValue("colors/palette", name)
        self.changed.emit()

    def color(self, category: str, value: object) -> QColor:
        key = self._normalize(value)
        if not key:
            return QColor()
        override = self._overrides.get((category, key))
        if override:
            return QColor(override)
        palette = PALETTES[self._palette_name]
        mapping = self._palette_mapping(category)
        configured = mapping.get(key)
        if configured:
            return QColor(configured)
        automatic = self._automatic_colors.get((category, key))
        if automatic:
            return QColor(automatic)
        digest = int.from_bytes(sha1(f"{category}:{key}".encode("utf-8")).digest()[:4], "big")
        return QColor(palette.fallback_colors[digest % len(palette.fallback_colors)])

    def next_color(self, category: str) -> QColor:
        """Return the next palette-cycle color for *category*."""
        palette = PALETTES[self._palette_name]
        cycle = palette.fallback_colors
        configured_colors = {
            QColor(raw).name(QColor.HexRgb).lower() for raw in self._palette_mapping(category).values()
        }

        base_count = 0
        for raw in cycle:
            if QColor(raw).name(QColor.HexRgb).lower() not in configured_colors:
                break
            base_count += 1

        allocated_count = sum(1 for namespace, _key in self._automatic_colors if namespace == category)
        allocated_count += len(self._custom_values.get(category, ()))
        return QColor(cycle[(base_count + allocated_count) % len(cycle)])

    def set_override(self, category: str, value: str, color: QColor) -> None:
        key = self._normalize(value)
        if not key or not color.isValid():
            return
        self._overrides[(category, key)] = color.name(QColor.HexRgb)
        self._known_values.setdefault(category, set()).add(key)
        self._save_overrides()
        self.changed.emit()

    def clear_override(self, category: str, value: str) -> None:
        key = self._normalize(value)
        if self._overrides.pop((category, key), None) is not None:
            self._save_overrides()
            self.changed.emit()

    def override(self, category: str, value: str) -> QColor | None:
        raw = self._overrides.get((category, self._normalize(value)))
        return QColor(raw) if raw else None

    def register_values(self, category: str, values: Iterable[object]) -> None:
        known = self._known_values.setdefault(category, set())
        configured = self._palette_mapping(category)
        custom = self._custom_values.get(category, ())
        for value in values:
            key = self._normalize(value)
            if not key:
                continue
            is_new = key not in known
            known.add(key)
            if (
                is_new
                and key not in configured
                and key not in custom
                and (category, key) not in self._overrides
                and (category, key) not in self._automatic_colors
            ):
                self._automatic_colors[(category, key)] = self.next_color(category).name(QColor.HexRgb)

    def add_custom_value(self, category: str, value: str, color: QColor | None = None) -> str:
        key = self._normalize(value)
        if not key:
            raise ValueError("Color mapping value cannot be empty")
        if key in self.values(category):
            raise ValueError(f"Color mapping already exists: {key}")
        assigned_color = color or self.next_color(category)
        self._custom_values.setdefault(category, []).append(key)
        self._known_values.setdefault(category, set()).add(key)
        self._overrides[(category, key)] = assigned_color.name(QColor.HexRgb)
        self._save_custom_values()
        self._save_overrides()
        self.changed.emit()
        return key

    def rename_custom_value(self, category: str, old_value: str, new_value: str) -> str:
        old_key = self._normalize(old_value)
        new_key = self._normalize(new_value)
        if not new_key:
            raise ValueError("Color mapping value cannot be empty")
        custom = self._custom_values.setdefault(category, [])
        if old_key not in custom:
            raise ValueError(f"Not a custom color mapping: {old_key}")
        if new_key != old_key and new_key in self.values(category):
            raise ValueError(f"Color mapping already exists: {new_key}")
        index = custom.index(old_key)
        custom[index] = new_key
        color = self._overrides.pop((category, old_key), None)
        if color is not None:
            self._overrides[(category, new_key)] = color
        self._known_values.setdefault(category, set()).discard(old_key)
        self._known_values[category].add(new_key)
        self._save_custom_values()
        self._save_overrides()
        self.changed.emit()
        return new_key

    def remove_custom_value(self, category: str, value: str) -> None:
        key = self._normalize(value)
        custom = self._custom_values.setdefault(category, [])
        if key not in custom:
            return
        custom.remove(key)
        self._overrides.pop((category, key), None)
        self._known_values.setdefault(category, set()).discard(key)
        self._save_custom_values()
        self._save_overrides()
        self.changed.emit()

    def is_custom_value(self, category: str, value: str) -> bool:
        return self._normalize(value) in self._custom_values.get(category, ())

    def values(self, category: str) -> tuple[str, ...]:
        defaults = self._palette_mapping(category)
        custom = self._custom_values.get(category, [])
        other = sorted(
            (self._known_values.get(category, set()) | {key for namespace, key in self._overrides if namespace == category})
            - set(defaults)
            - set(custom)
        )
        return tuple([*defaults, *custom, *other])

    def _palette_mapping(self, category: str) -> dict[str, str]:
        palette = PALETTES[self._palette_name]
        return palette.type_colors if category == TYPE_CATEGORY else palette.assignment_colors

    def _load_overrides(self) -> None:
        self._settings.beginGroup("colors/overrides")
        for category in self._settings.childGroups():
            self._settings.beginGroup(category)
            for key in self._settings.childKeys():
                value = str(self._settings.value(key))
                if QColor(value).isValid():
                    self._overrides[(category, key)] = value
            self._settings.endGroup()
        self._settings.endGroup()

    def _save_overrides(self) -> None:
        self._settings.remove("colors/overrides")
        for (category, key), color in self._overrides.items():
            self._settings.setValue(f"colors/overrides/{category}/{key}", color)

    def _load_custom_values(self) -> None:
        for category in (TYPE_CATEGORY, ASSIGNMENT_CATEGORY):
            raw = self._settings.value(f"colors/custom_values/{category}", [])
            values = [raw] if isinstance(raw, str) else list(raw or [])
            self._custom_values[category] = [self._normalize(value) for value in values if self._normalize(value)]
            self._known_values[category].update(self._custom_values[category])

    def _save_custom_values(self) -> None:
        for category, values in self._custom_values.items():
            self._settings.setValue(f"colors/custom_values/{category}", values)

    @staticmethod
    def _normalize(value: object) -> str:
        return "" if value is None else str(value).strip().upper()


class ColorSettingsDialog(QDialog):
    """Standard Qt settings dialog for palette selection and semantic color overrides."""

    COLOR_COLUMN = 2

    def __init__(
        self,
        theme: ColorTheme,
        parent: QWidget | None = None,
        *,
        editor_preferences: EditorPreferences | None = None,
        application_preferences: ApplicationPreferences | None = None,
    ) -> None:
        super().__init__(parent)
        self.theme = theme
        self.editor_preferences = editor_preferences
        self.application_preferences = application_preferences
        self.setWindowTitle("Project Generation Settings")
        self.resize(620, 520)

        self.palette_combo = QComboBox()
        self.palette_combo.addItems(PALETTES)
        self.palette_combo.setCurrentText(theme.palette_name)
        self.palette_combo.currentTextChanged.connect(self._palette_changed)

        palette_form = QFormLayout()
        palette_form.addRow("Color palette", self.palette_combo)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Category", "Value", "Color"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.cellDoubleClicked.connect(self._cell_double_clicked)
        self.table.itemSelectionChanged.connect(self._update_buttons)

        self.add_button = QPushButton("Add…")
        self.add_button.clicked.connect(self._add_value)
        self.rename_button = QPushButton("Rename…")
        self.rename_button.clicked.connect(self._rename_selected)
        self.remove_button = QPushButton("Remove")
        self.remove_button.clicked.connect(self._remove_selected)
        reset_button = QPushButton("Reset Color")
        reset_button.clicked.connect(self._reset_selected)
        button_row = QHBoxLayout()
        button_row.addWidget(self.add_button)
        button_row.addWidget(self.rename_button)
        button_row.addWidget(self.remove_button)
        button_row.addWidget(reset_button)
        button_row.addStretch(1)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)

        colors_page = QWidget()
        colors_layout = QVBoxLayout(colors_page)
        colors_layout.addLayout(palette_form)
        colors_layout.addWidget(QLabel("Double-click only the Color column to choose a color."))
        colors_layout.addWidget(self.table)
        colors_layout.addLayout(button_row)

        tabs = QTabWidget()
        if application_preferences is not None:
            general_page = QWidget()
            general_form = QFormLayout(general_page)

            self.default_export_path_edit = QLineEdit(str(application_preferences.default_export_path))
            self.default_export_path_edit.editingFinished.connect(
                lambda: application_preferences.set_default_export_path(self.default_export_path_edit.text())
            )
            browse_export_path = QPushButton("Browse…")
            browse_export_path.clicked.connect(self._browse_default_export_path)
            export_path_row = QWidget()
            export_path_layout = QHBoxLayout(export_path_row)
            export_path_layout.setContentsMargins(0, 0, 0, 0)
            export_path_layout.addWidget(self.default_export_path_edit, 1)
            export_path_layout.addWidget(browse_export_path)
            general_form.addRow("Default export path", export_path_row)

            self.open_exported_folder_checkbox = QCheckBox("Open exported folder when export completes")
            self.open_exported_folder_checkbox.setChecked(application_preferences.open_folder_after_export)
            self.open_exported_folder_checkbox.toggled.connect(
                application_preferences.set_open_folder_after_export
            )
            general_form.addRow("", self.open_exported_folder_checkbox)

            self.restore_last_session_checkbox = QCheckBox("Restore last session on startup")
            self.restore_last_session_checkbox.setChecked(application_preferences.restore_last_session)
            self.restore_last_session_checkbox.toggled.connect(
                application_preferences.set_restore_last_session
            )
            general_form.addRow("Sessions", self.restore_last_session_checkbox)
            tabs.addTab(general_page, "General")
        if editor_preferences is not None:
            editor_page = QWidget()
            editor_form = QFormLayout(editor_page)

            self.theme_combo = QComboBox()
            self.theme_combo.addItems(THEMES)
            self.theme_combo.setCurrentText(editor_preferences.theme)
            self.theme_combo.currentTextChanged.connect(editor_preferences.set_theme)
            editor_form.addRow("Theme", self.theme_combo)

            self.font_size_spin = QSpinBox()
            self.font_size_spin.setRange(6, 48)
            self.font_size_spin.setSuffix(" pt")
            self.font_size_spin.setValue(editor_preferences.font_size)
            self.font_size_spin.valueChanged.connect(editor_preferences.set_font_size)
            editor_form.addRow("Editor font size", self.font_size_spin)

            tabs.addTab(editor_page, "Editor")
        tabs.addTab(colors_page, "Colors")

        layout = QVBoxLayout(self)
        layout.addWidget(tabs)
        layout.addWidget(buttons)
        self._populate()

    def _browse_default_export_path(self) -> None:
        if self.application_preferences is None:
            return
        path = QFileDialog.getExistingDirectory(
            self,
            "Default Export Path",
            self.default_export_path_edit.text(),
        )
        if not path:
            return
        self.default_export_path_edit.setText(path)
        self.application_preferences.set_default_export_path(path)

    def _populate(self) -> None:
        selected = self._selected_mapping()
        self.table.setRowCount(0)
        selected_row = -1
        for category, label in ((TYPE_CATEGORY, "Pin / Group Type"), (ASSIGNMENT_CATEGORY, "Assignment")):
            for value in self.theme.values(category):
                row = self.table.rowCount()
                self.table.insertRow(row)
                category_item = QTableWidgetItem(label)
                category_item.setData(Qt.UserRole, category)
                value_item = QTableWidgetItem(value)
                swatch = QTableWidgetItem(self.theme.color(category, value).name())
                swatch.setForeground(self.theme.color(category, value))
                override = self.theme.override(category, value)
                if override is not None:
                    swatch.setText(f"{override.name()} (custom)")
                self.table.setItem(row, 0, category_item)
                self.table.setItem(row, 1, value_item)
                self.table.setItem(row, 2, swatch)
                if selected == (category, value):
                    selected_row = row
        if selected_row >= 0:
            self.table.selectRow(selected_row)
        self._update_buttons()

    def _palette_changed(self, name: str) -> None:
        self.theme.set_palette(name)
        self._populate()

    def _cell_double_clicked(self, row: int, column: int) -> None:
        if column == self.COLOR_COLUMN:
            self._choose_color(row)

    def _choose_color(self, row: int) -> None:
        category = self.table.item(row, 0).data(Qt.UserRole)
        value = self.table.item(row, 1).text()
        color = QColorDialog.getColor(self.theme.color(category, value), self, f"Color for {value}")
        if color.isValid():
            self.theme.set_override(category, value, color)
            self._populate()

    def _reset_selected(self) -> None:
        mapping = self._selected_mapping()
        if mapping is None:
            return
        self.theme.clear_override(*mapping)
        self._populate()

    def _add_value(self) -> None:
        labels = {"Pin / Group Type": TYPE_CATEGORY, "Assignment": ASSIGNMENT_CATEGORY}
        label, accepted = QInputDialog.getItem(self, "Add Color Entry", "Category", list(labels), editable=False)
        if not accepted:
            return
        value, accepted = QInputDialog.getText(self, "Add Color Entry", "Value")
        if not accepted or not value.strip():
            return
        category = labels[label]
        try:
            self.theme.add_custom_value(category, value, self.theme.next_color(category))
        except ValueError as exc:
            from qtpy.QtWidgets import QMessageBox

            QMessageBox.warning(self, "Add Color Entry", str(exc))
        self._populate()

    def _rename_selected(self) -> None:
        mapping = self._selected_mapping()
        if mapping is None:
            return
        category, value = mapping
        if not self.theme.is_custom_value(category, value):
            return
        new_value, accepted = QInputDialog.getText(self, "Rename Color Entry", "Value", text=value)
        if not accepted or not new_value.strip():
            return
        try:
            self.theme.rename_custom_value(category, value, new_value)
        except ValueError as exc:
            from qtpy.QtWidgets import QMessageBox

            QMessageBox.warning(self, "Rename Color Entry", str(exc))
        self._populate()

    def _remove_selected(self) -> None:
        mapping = self._selected_mapping()
        if mapping is None:
            return
        category, value = mapping
        if not self.theme.is_custom_value(category, value):
            return
        self.theme.remove_custom_value(category, value)
        self._populate()

    def _selected_mapping(self) -> tuple[str, str] | None:
        row = self.table.currentRow()
        if row < 0 or self.table.item(row, 0) is None:
            return None
        category = self.table.item(row, 0).data(Qt.UserRole)
        value = self.table.item(row, 1).text()
        return category, value

    def _update_buttons(self) -> None:
        mapping = self._selected_mapping()
        editable = mapping is not None and self.theme.is_custom_value(*mapping)
        self.rename_button.setEnabled(editable)
        self.remove_button.setEnabled(editable)
