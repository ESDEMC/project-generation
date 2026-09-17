import json
from dataclasses import dataclass, fields, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Sequence
from uuid import UUID

from pydantic import BaseModel
from qtpy.QtCore import QEvent, QModelIndex, QSortFilterProxyModel, Qt, Signal
from qtpy.QtGui import (
    QColor,
    QFontDatabase,
    QKeySequence,
    QStandardItem,
    QStandardItemModel,
    QTextCursor,
)
from qtpy.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QShortcut,
    QSplitter,
    QStyledItemDelegate,
    QStyle,
    QStyleOptionViewItem,
    QTableView,
    QTabWidget,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from project_generation.generation.models import (
    GeneratedDeviceState,
    GeneratedGroup,
    GeneratedPin,
    GeneratedTestPlan,
)
from project_generation.generation.snapshot import GenerationSnapshot
from project_generation_gui.colors import ASSIGNMENT_CATEGORY, TYPE_CATEGORY, ColorTheme
from project_generation_gui.power_envelope import (
    PowerEnvelopeComparisonView,
    PowerEnvelopeGridView,
    requested_configuration_from_bias,
    requested_configurations_from_stress,
)
from project_generation_gui.syntax_highlighting import PygmentsSearchHighlighter, style_name_for_background


class TextEditor(QPlainTextEdit):
    document_text_changed = Signal(str)

    def __init__(self, path: Path, text: str, parent=None) -> None:
        # Qt may dispatch events while the base widget is still being constructed.
        # Initialize attributes used by eventFilter before QPlainTextEdit.__init__.
        self.search_edit: QLineEdit | None = None
        self._search_matches: list[tuple[int, int]] = []
        self._search_index = -1
        self._search_navigation_valid = False
        self._search_cursor_move_in_progress = False
        self._search_shortcuts: list[QShortcut] = []

        super().__init__(parent)
        self.path = path

        self.setPlainText(text)
        self.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
        self._search_highlighter = PygmentsSearchHighlighter(
            self.document(),
            self.path,
            self.palette().highlight().color(),
            style_name=style_name_for_background(self.palette().base().color()),
        )
        self.textChanged.connect(self._text_changed)
        self.cursorPositionChanged.connect(self._editor_cursor_moved)

        self.search_bar = QWidget(self)
        search_layout = QHBoxLayout(self.search_bar)
        search_layout.setContentsMargins(6, 3, 4, 3)
        search_layout.setSpacing(4)

        self.search_edit = QLineEdit(self.search_bar)
        self.search_edit.setPlaceholderText("Find")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.textChanged.connect(self._search_text_changed)
        self.search_edit.installEventFilter(self)

        self.search_count = QLabel("0/0", self.search_bar)
        self.search_count.setMinimumWidth(48)
        self.search_count.setAlignment(Qt.AlignCenter)

        self.search_previous_button = QToolButton(self.search_bar)
        self.search_previous_button.setText("↑")
        self.search_previous_button.setToolTip("Previous match (Shift+Enter)")
        self.search_previous_button.clicked.connect(self.find_previous)

        self.search_next_button = QToolButton(self.search_bar)
        self.search_next_button.setText("↓")
        self.search_next_button.setToolTip("Next match (Enter)")
        self.search_next_button.clicked.connect(self.find_next)

        self.search_close_button = QToolButton(self.search_bar)
        self.search_close_button.setText("×")
        self.search_close_button.setToolTip("Close find (Esc)")
        self.search_close_button.clicked.connect(self.hide_search)

        search_layout.addWidget(self.search_edit, 1)
        search_layout.addWidget(self.search_count)
        search_layout.addWidget(self.search_previous_button)
        search_layout.addWidget(self.search_next_button)
        search_layout.addWidget(self.search_close_button)
        self.search_bar.hide()

        self._add_search_shortcut(QKeySequence.Find, self.show_search)
        self._add_search_shortcut(QKeySequence.FindNext, self.find_next)
        self._add_search_shortcut(QKeySequence.FindPrevious, self.find_previous)

    def _add_search_shortcut(self, sequence: QKeySequence, callback) -> None:
        shortcut = QShortcut(sequence, self)
        shortcut.setContext(Qt.WidgetWithChildrenShortcut)
        shortcut.activated.connect(callback)
        self._search_shortcuts.append(shortcut)

    def set_font_size(self, point_size: int) -> None:
        font = self.font()
        font.setPointSize(int(point_size))
        self.setFont(font)

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.PaletteChange:
            highlighter = getattr(self, "_search_highlighter", None)
            if highlighter is not None:
                highlighter.set_style_name(style_name_for_background(self.palette().base().color()))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        width = min(520, max(300, self.width() // 2))
        self.search_bar.adjustSize()
        height = self.search_bar.sizeHint().height()
        self.search_bar.setGeometry(self.width() - width - 12, 6, width, height)
        self.search_bar.raise_()

    def eventFilter(self, watched, event) -> bool:
        search_edit = self.search_edit
        if search_edit is not None and watched is search_edit and event.type() == QEvent.KeyPress:
            if event.key() in (Qt.Key_Return, Qt.Key_Enter):
                if event.modifiers() & Qt.ShiftModifier:
                    self.find_previous()
                else:
                    self.find_next()
                return True
            if event.key() == Qt.Key_Escape:
                self.hide_search()
                return True
        return super().eventFilter(watched, event)

    def show_search(self) -> None:
        selected_text = self.textCursor().selectedText()
        if selected_text and "\n" not in selected_text:
            self.search_edit.setText(selected_text)
        self.search_bar.show()
        self.search_bar.raise_()
        self.search_edit.setFocus()
        self.search_edit.selectAll()
        self._update_search_matches(preserve_current=True)

    def hide_search(self) -> None:
        self.search_bar.hide()
        self._search_index = -1
        self._search_navigation_valid = False
        self._search_highlighter.set_matches([], None)
        self.setFocus()

    def find_next(self) -> None:
        self._navigate_search(1)

    def find_previous(self) -> None:
        self._navigate_search(-1)

    def _text_changed(self) -> None:
        self.document_text_changed.emit(self.toPlainText())
        if self.search_bar.isVisible():
            # Edits invalidate the previous navigation anchor. Recompute matches,
            # but leave the editor cursor and selection entirely untouched.
            self._search_navigation_valid = False
            self._update_search_matches(preserve_current=True)

    def _editor_cursor_moved(self) -> None:
        if self._search_cursor_move_in_progress:
            return
        if self.hasFocus() and self.search_bar.isVisible():
            self._search_navigation_valid = False

    def _search_text_changed(self) -> None:
        self._search_navigation_valid = False
        self._update_search_matches(preserve_current=False)
        if self._search_matches:
            self._search_index = self._match_index_from_cursor(1)
            self._search_navigation_valid = True
            self._refresh_search_highlights()
            self._update_search_count()

    def _update_search_matches(self, *, preserve_current: bool) -> None:
        query = self.search_edit.text()
        previous_match = self._current_search_match() if preserve_current else None
        self._search_matches = []
        self._search_index = -1

        if query:
            document = self.document()
            cursor = QTextCursor(document)
            while True:
                cursor = document.find(query, cursor)
                if cursor.isNull():
                    break
                self._search_matches.append((cursor.selectionStart(), cursor.selectionEnd()))

        if previous_match in self._search_matches:
            self._search_index = self._search_matches.index(previous_match)
        else:
            self._search_navigation_valid = False

        # A query with no matches must not leave stale highlighting behind.
        current_match = self._current_search_match() if self._search_navigation_valid else None
        self._search_highlighter.set_matches(self._search_matches, current_match)
        self._update_search_count()

    def _navigate_search(self, step: int) -> None:
        if not self.search_edit.text():
            self._clear_search_state()
            return

        if not self._search_matches:
            self._update_search_matches(preserve_current=False)
            if not self._search_matches:
                return

        if self._search_navigation_valid and 0 <= self._search_index < len(self._search_matches):
            self._search_index = (self._search_index + step) % len(self._search_matches)
        else:
            self._search_index = self._match_index_from_cursor(step)

        self._search_navigation_valid = True
        self._refresh_search_highlights()
        self._update_search_count()
        self._select_current_match()

    def _match_index_from_cursor(self, step: int) -> int:
        position = self.textCursor().position()
        if step > 0:
            return next(
                (index for index, (start, _end) in enumerate(self._search_matches) if start >= position),
                0,
            )
        return next(
            (
                index
                for index in range(len(self._search_matches) - 1, -1, -1)
                if self._search_matches[index][1] <= position
            ),
            len(self._search_matches) - 1,
        )

    def _current_search_match(self) -> tuple[int, int] | None:
        if 0 <= self._search_index < len(self._search_matches):
            return self._search_matches[self._search_index]
        return None

    def _select_current_match(self) -> None:
        current_match = self._current_search_match()
        if current_match is None:
            return

        start, end = current_match
        cursor = QTextCursor(self.document())
        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.KeepAnchor)

        # Moving the editor cursor is intentional search navigation. Do not let
        # cursorPositionChanged invalidate the search state that initiated it.
        self._search_cursor_move_in_progress = True
        try:
            self.setTextCursor(cursor)
            self.ensureCursorVisible()
        finally:
            self._search_cursor_move_in_progress = False

    def _refresh_search_highlights(self) -> None:
        current_match = self._current_search_match() if self._search_navigation_valid else None
        self._search_highlighter.set_matches(self._search_matches, current_match)

    def _clear_search_state(self) -> None:
        self._search_matches = []
        self._search_index = -1
        self._search_navigation_valid = False
        self._search_highlighter.set_matches([], None)
        self._update_search_count()

    def _update_search_count(self) -> None:
        total = len(self._search_matches)
        current = self._search_index + 1 if total and self._search_navigation_valid else 0
        self.search_count.setText(f"{current}/{total}")


class EditorArea(QWidget):
    """Single tabbed central workspace for documents and generated views."""

    editor_closed = Signal(QWidget)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._tabs = QTabWidget(self)
        self._tabs.setDocumentMode(True)
        self._tabs.setMovable(True)
        self._tabs.setTabsClosable(True)
        self._tabs.tabCloseRequested.connect(self._close_tab)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._tabs)

    def add_editor(self, editor: QWidget, title: str) -> None:
        index = self._tabs.indexOf(editor)
        if index < 0:
            index = self._tabs.addTab(editor, title)
        else:
            self._tabs.setTabText(index, title)
        self._tabs.setCurrentIndex(index)
        editor.setFocus()

    def current_editor(self) -> QWidget | None:
        return self._tabs.currentWidget()

    def set_current_editor(self, editor: QWidget) -> None:
        index = self._tabs.indexOf(editor)
        if index < 0:
            return
        self._tabs.setCurrentIndex(index)
        editor.setFocus()

    def contains_editor(self, editor: QWidget) -> bool:
        return self._tabs.indexOf(editor) >= 0

    def iter_editors(self):
        for index in range(self._tabs.count()):
            yield self._tabs, index, self._tabs.widget(index)

    def set_editor_title(self, editor: QWidget, title: str) -> None:
        index = self._tabs.indexOf(editor)
        if index >= 0:
            self._tabs.setTabText(index, title)

    def _close_tab(self, index: int) -> None:
        editor = self._tabs.widget(index)
        if editor is None:
            return
        self._tabs.removeTab(index)
        self.editor_closed.emit(editor)


class ObjectTree(QTreeWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setHeaderLabels(["Name", "Value"])
        self.setAlternatingRowColors(True)

    def set_value(self, value: Any) -> None:
        self.clear()
        self._append(self.invisibleRootItem(), "root", value)
        self.expandToDepth(1)

    def _append(self, parent: QTreeWidgetItem, name: str, value: Any) -> None:
        if isinstance(value, BaseModel):
            value = value.model_dump(mode="python", by_alias=True)
        elif is_dataclass(value) and not isinstance(value, type):
            value = {field.name: getattr(value, field.name) for field in fields(value)}

        if isinstance(value, Mapping):
            item = QTreeWidgetItem([name, f"{{{len(value)}}}"])
            parent.addChild(item)
            for key, child in value.items():
                self._append(item, str(key), child)
        elif isinstance(value, (list, tuple)):
            item = QTreeWidgetItem([name, f"[{len(value)}]"])
            parent.addChild(item)
            for index, child in enumerate(value):
                self._append(item, f"[{index}]", child)
        else:
            if isinstance(value, Enum):
                value = value.value
            elif isinstance(value, UUID):
                value = str(value)
            parent.addChild(QTreeWidgetItem([name, "" if value is None else str(value)]))


RICH_TEXT_ROLE = Qt.UserRole + 1


@dataclass(frozen=True)
class StyledValue:
    value: Any
    category: str | None = None
    color_key: object | None = None
    segments: tuple[tuple[str, str | None, object | None], ...] = ()
    foreground: QColor | None = None
    tooltip: str | None = None


class RichTextDelegate(QStyledItemDelegate):
    """Wrap the standard item delegate while adding per-segment semantic colors."""

    def __init__(self, theme: ColorTheme, parent=None) -> None:
        super().__init__(parent)
        self.theme = theme

    def paint(self, painter, option, index) -> None:
        segments = index.data(RICH_TEXT_ROLE)
        if not segments:
            super().paint(painter, option, index)
            return

        # Let Qt paint the normal cell background, selection, focus indicator, and
        # spacing. Only suppress its text so our segment colors use exactly the
        # same text rectangle and vertical alignment as neighboring cells.
        styled_option = QStyleOptionViewItem(option)
        self.initStyleOption(styled_option, index)
        styled_option.text = ""
        style = styled_option.widget.style() if styled_option.widget is not None else QApplication.style()
        style.drawControl(QStyle.CE_ItemViewItem, styled_option, painter, styled_option.widget)

        text_rect = style.subElementRect(QStyle.SE_ItemViewItemText, styled_option, styled_option.widget)
        painter.setFont(styled_option.font)
        font_metrics = styled_option.fontMetrics
        segment_widths = [font_metrics.horizontalAdvance(text) for text, _category, _key in segments]
        total_width = sum(segment_widths)

        if styled_option.displayAlignment & Qt.AlignRight:
            x = text_rect.right() - total_width + 1
        elif styled_option.displayAlignment & Qt.AlignHCenter:
            x = text_rect.left() + (text_rect.width() - total_width) / 2
        else:
            x = text_rect.left()
        baseline = text_rect.top() + (text_rect.height() - font_metrics.height()) / 2 + font_metrics.ascent()

        default_color = (
            option.palette.highlightedText().color()
            if option.state & QStyle.State_Selected
            else option.palette.text().color()
        )
        painter.save()
        painter.setClipRect(text_rect)
        for (segment_text, category, key), width in zip(segments, segment_widths):
            painter.setPen(self.theme.color(category, key) if category and key else default_color)
            painter.drawText(int(x), int(baseline), segment_text)
            x += width
        painter.restore()


class GeneratedItemsTable(QTableView):
    """Read-only table backed by a standard Qt item model."""

    def __init__(self, theme: ColorTheme, parent=None) -> None:
        super().__init__(parent)
        self.theme = theme
        self._source_model = QStandardItemModel(self)
        self._proxy_model = QSortFilterProxyModel(self)
        self._proxy_model.setSourceModel(self._source_model)
        self.setModel(self._proxy_model)
        self.setItemDelegate(RichTextDelegate(theme, self))
        self.setSortingEnabled(False)
        self.horizontalHeader().setSectionsClickable(False)
        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)

    def set_rows(self, headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> None:
        self._source_model.clear()
        self._source_model.setHorizontalHeaderLabels(list(headers))
        for row in rows:
            self._source_model.appendRow([self._make_item(value) for value in row])
        self.resizeColumnsToContents()
        self.viewport().update()

    def refresh_colors(self) -> None:
        for row in range(self._source_model.rowCount()):
            for column in range(self._source_model.columnCount()):
                item = self._source_model.item(row, column)
                if item is None:
                    continue
                category = item.data(Qt.UserRole + 2)
                key = item.data(Qt.UserRole + 3)
                if category and key:
                    item.setForeground(self.theme.color(category, key))
        self.viewport().update()

    def _make_item(self, value: Any) -> QStandardItem:
        styled = value if isinstance(value, StyledValue) else StyledValue(value=value)
        item = QStandardItem(_display_value(styled.value))
        if styled.category is not None and styled.color_key is not None:
            item.setForeground(self.theme.color(styled.category, styled.color_key))
            item.setData(styled.category, Qt.UserRole + 2)
            item.setData(str(styled.color_key), Qt.UserRole + 3)
        if styled.foreground is not None:
            item.setForeground(styled.foreground)
        if styled.tooltip:
            item.setToolTip(styled.tooltip)
        if styled.segments:
            item.setData(styled.segments, RICH_TEXT_ROLE)
        return item


def _styled_group_names(
    group_names: Sequence[str], groups_by_name: Mapping[str, GeneratedGroup]
) -> StyledValue:
    segments = []
    for index, name in enumerate(group_names):
        if index:
            segments.append((", ", None, None))
        group = groups_by_name.get(name)
        segments.append((name, TYPE_CATEGORY, group.group_type if group is not None else ""))
    return StyledValue(", ".join(group_names), segments=tuple(segments))


def _set_power_domains_table(
    table: GeneratedItemsTable,
    state: GeneratedDeviceState | None,
    groups_by_name: Mapping[str, GeneratedGroup],
) -> None:
    if state is None:
        table.set_rows([], [])
        return

    timing_keys = sorted(
        {
            key
            for domain in state.power_domains
            if domain.timing is not None
            for key in domain.timing
        }
    )
    bias_keys = sorted({key for domain in state.power_domains for key in domain.bias})
    headers = ["Domain", "Assignment", "Groups", *[f"Bias: {key}" for key in bias_keys]]
    headers.extend(f"Timing: {key}" for key in timing_keys)
    rows = []
    for domain in state.power_domains:
        timing = domain.timing or {}
        rows.append(
            [
                domain.name,
                StyledValue(domain.assignment, ASSIGNMENT_CATEGORY, domain.assignment),
                _styled_group_names(domain.group_names, groups_by_name),
                *(domain.bias.get(key) for key in bias_keys),
                *(timing.get(key) for key in timing_keys),
            ]
        )
    table.set_rows(headers, rows)


class DeviceStatesView(QWidget):
    """Master/detail view that preserves the structure of generated device states."""

    def __init__(self, theme: ColorTheme, parent=None) -> None:
        super().__init__(parent)
        self.theme = theme
        self._groups_by_name: dict[str, GeneratedGroup] = {}
        self._stress_point_contexts: list[tuple[Mapping[str, Any], Any]] = []
        self._states: tuple[GeneratedDeviceState, ...] = ()
        self.state_list = QListWidget()
        self.state_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.state_list.currentRowChanged.connect(self._state_selected)

        self.summary = ObjectTree()
        self.power_domains = GeneratedItemsTable(theme)
        self.power_on = GeneratedItemsTable(theme)
        self.power_off = GeneratedItemsTable(theme)

        self.details = QTabWidget()
        self.details.addTab(self.power_domains, "Power Domains")
        self.details.addTab(self.power_on, "Power On Sequence")
        self.details.addTab(self.power_off, "Power Off Sequence")
        self.details.addTab(self.summary, "Details")

        splitter = QSplitter(Qt.Horizontal)
        selector = QWidget()
        selector_layout = QVBoxLayout(selector)
        selector_layout.setContentsMargins(0, 0, 0, 0)
        selector_layout.addWidget(QLabel("Device States"))
        selector_layout.addWidget(self.state_list)
        splitter.addWidget(selector)
        splitter.addWidget(self.details)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 4)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(splitter)

    def set_states(self, states: Sequence[GeneratedDeviceState], groups: Sequence[GeneratedGroup]) -> None:
        self._groups_by_name = {group.name: group for group in groups}
        previous_name = self.current_state_name()
        self._states = tuple(states)
        self.state_list.clear()
        for state in self._states:
            item = QListWidgetItem(state.name)
            item.setToolTip(f"Extends: {state.extends}" if state.extends else state.name)
            self.state_list.addItem(item)

        if not self._states:
            self._clear_details()
            return

        selected_index = 0
        if previous_name is not None:
            selected_index = next(
                (index for index, state in enumerate(self._states) if state.name == previous_name),
                0,
            )
        self.state_list.setCurrentRow(selected_index)

    def current_state_name(self) -> str | None:
        row = self.state_list.currentRow()
        if 0 <= row < len(self._states):
            return self._states[row].name
        return None

    def _state_selected(self, row: int) -> None:
        if not 0 <= row < len(self._states):
            self._clear_details()
            return
        state = self._states[row]
        self._set_power_domains(state)
        self._set_sequence(self.power_on, state.power_on_sequence)
        self._set_sequence(self.power_off, state.power_off_sequence)
        self.summary.set_value(
            {
                "name": state.name,
                "extends": state.extends,
                "id": state.id,
                "power_domain_count": len(state.power_domains),
                "power_on_step_count": len(state.power_on_sequence),
                "power_off_step_count": len(state.power_off_sequence),
            }
        )

    def _set_power_domains(self, state: GeneratedDeviceState) -> None:
        _set_power_domains_table(self.power_domains, state, self._groups_by_name)

    def _set_sequence(self, table: GeneratedItemsTable, sequence: Sequence[Any]) -> None:
        table.set_rows(
            ["Step", "Domain", "Assignment", "Groups", "Bias", "Delay", "After"],
            [
                [
                    step.index,
                    step.domain_name,
                    StyledValue(step.assignment, ASSIGNMENT_CATEGORY, step.assignment),
                    _styled_group_names(step.group_names, self._groups_by_name),
                    step.bias,
                    step.delay,
                    step.after,
                ]
                for step in sequence
            ],
        )


    def _clear_details(self) -> None:
        self.power_domains.set_rows([], [])
        self.power_on.set_rows([], [])
        self.power_off.set_rows([], [])
        self.summary.clear()


class TestPlansView(QWidget):
    """Master/detail view for generated test plans and their nested test groups."""

    def __init__(self, theme: ColorTheme, parent=None) -> None:
        super().__init__(parent)
        self.theme = theme
        self._plans: tuple[GeneratedTestPlan, ...] = ()
        self._groups_by_id: dict[UUID, GeneratedGroup] = {}
        self._pins_by_id: dict[UUID, GeneratedPin] = {}
        self._device_states_by_id: dict[UUID, GeneratedDeviceState] = {}
        self._device_states_by_name: dict[str, GeneratedDeviceState] = {}
        self._groups_by_name: dict[str, GeneratedGroup] = {}
        self._stress_point_contexts: list[tuple[Mapping[str, Any], Any]] = []
        self.plan_list = QListWidget()
        self.plan_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.plan_list.currentRowChanged.connect(self._plan_selected)

        self.summary = ObjectTree()
        self.groups = GeneratedItemsTable(theme)
        self.stress_points = GeneratedItemsTable(theme)
        self.stress_device_state = GeneratedItemsTable(theme)
        self.stress_device_state_label = QLabel("Device State")
        self.power_envelope = PowerEnvelopeGridView(theme)
        self._power_resources: Mapping[str, Any] = {}

        stress_page = QWidget()
        stress_layout = QVBoxLayout(stress_page)
        stress_layout.setContentsMargins(0, 0, 0, 0)
        stress_splitter = QSplitter(Qt.Vertical)

        stress_points_panel = QWidget()
        stress_points_layout = QVBoxLayout(stress_points_panel)
        stress_points_layout.setContentsMargins(0, 0, 0, 0)
        stress_points_layout.addWidget(QLabel("Stress Points"))
        stress_points_layout.addWidget(self.stress_points)

        device_state_panel = QWidget()
        device_state_layout = QVBoxLayout(device_state_panel)
        device_state_layout.setContentsMargins(0, 0, 0, 0)
        device_state_layout.addWidget(self.stress_device_state_label)
        device_state_layout.addWidget(self.stress_device_state)

        stress_splitter.addWidget(stress_points_panel)
        stress_splitter.addWidget(device_state_panel)
        stress_splitter.setStretchFactor(0, 3)
        stress_splitter.setStretchFactor(1, 2)
        stress_layout.addWidget(stress_splitter)

        self.details = QTabWidget()
        self.details.addTab(stress_page, "Stress Points")
        self.details.addTab(self.power_envelope, "Power Envelope")
        self.details.addTab(self.groups, "Test Groups")
        self.details.addTab(self.summary, "Details")

        splitter = QSplitter(Qt.Horizontal)
        selector = QWidget()
        selector_layout = QVBoxLayout(selector)
        selector_layout.setContentsMargins(0, 0, 0, 0)
        selector_layout.addWidget(QLabel("Test Plans"))
        selector_layout.addWidget(self.plan_list)
        splitter.addWidget(selector)
        splitter.addWidget(self.details)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 4)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(splitter)

    def set_plans(
        self,
        plans: Sequence[GeneratedTestPlan],
        groups: Sequence[GeneratedGroup],
        pins: Sequence[GeneratedPin],
        device_states: Sequence[GeneratedDeviceState],
        power_resources: Mapping[str, Any],
    ) -> None:
        previous_name = self.current_plan_name()
        self._plans = tuple(plans)
        self._groups_by_id = {group.id: group for group in groups}
        self._groups_by_name = {group.name: group for group in groups}
        self._pins_by_id = {pin.id: pin for pin in pins}
        self._device_states_by_id = {state.id: state for state in device_states}
        self._device_states_by_name = {state.name: state for state in device_states}
        self._power_resources = power_resources
        self.power_envelope.set_power_resources(power_resources)
        self.plan_list.clear()
        for plan in self._plans:
            item = QListWidgetItem(plan.name)
            if plan.hardware_issues:
                item.setForeground(QColor("#EF5350"))
                issue_text = "\n".join(
                    reason
                    for issue in plan.hardware_issues
                    for reason in issue.reasons
                )
                item.setToolTip(issue_text or "Stress settings exceed configured hardware capability")
            else:
                item.setToolTip(plan.test_type)
            self.plan_list.addItem(item)

        if not self._plans:
            self._clear_details()
            return

        selected_index = 0
        if previous_name is not None:
            selected_index = next(
                (index for index, plan in enumerate(self._plans) if plan.name == previous_name),
                0,
            )
        self.plan_list.setCurrentRow(selected_index)

    def current_plan_name(self) -> str | None:
        row = self.plan_list.currentRow()
        if 0 <= row < len(self._plans):
            return self._plans[row].name
        return None

    def _plan_selected(self, row: int) -> None:
        if not 0 <= row < len(self._plans):
            self._clear_details()
            return
        plan = self._plans[row]
        self.groups.set_rows(
            ["Group", "Pins", "Stress Points", "Stress Point Values"],
            [
                [
                    self._colored_group_name(group.group_id, group.group_name),
                    self._colored_pins(
                        self._groups_by_id.get(group.group_id),
                        pin_ids=group.pin_ids,
                    ),
                    len(group.stress_points),
                    group.stress_points,
                ]
                for group in plan.test_groups
            ],
        )
        self._set_stress_points(plan)
        self._set_stress_device_state(plan)
        self.summary.set_value(
            {
                "name": plan.name,
                "type": plan.test_type,
                "device_state": plan.device_state,
                "dimensions": plan.dimensions,
                "stress_supply": plan.stress_supply,
                "hardware_issues": plan.hardware_issues,
                "temperature_control": plan.temperature_control,
                "generation_rule_id": plan.generation_rule_id,
                "id": plan.id,
            }
        )

    def _set_stress_points(self, plan: GeneratedTestPlan) -> None:
        parameter_names = sorted(
            {
                name
                for test_group in plan.test_groups
                for stress_point in test_group.stress_points
                for name in stress_point.values
            }
        )
        rows = []
        self._stress_point_contexts = []
        issues_by_point = {
            (issue.group_name, issue.stress_point_index): issue
            for issue in plan.hardware_issues
        }
        for test_group in plan.test_groups:
            group = self._groups_by_id.get(test_group.group_id)
            pins = []
            if group is not None:
                pin_ids = test_group.pin_ids if test_group.pin_ids is not None else group.pin_ids
                pins = [
                    self._pins_by_id[pin_id].name or self._pins_by_id[pin_id].designator
                    for pin_id in pin_ids
                    if pin_id in self._pins_by_id
                ]
            for zero_based_index, stress_point in enumerate(test_group.stress_points):
                issue = issues_by_point.get((test_group.group_name, zero_based_index))
                tooltip = "\n".join(issue.reasons) if issue is not None else None
                parameter_values = []
                for name in parameter_names:
                    value = stress_point.values.get(name)
                    if issue is not None and isinstance(value, (int, float)) and not isinstance(value, bool):
                        value = StyledValue(value, foreground=QColor("#EF5350"), tooltip=tooltip)
                    parameter_values.append(value)
                self._stress_point_contexts.append((stress_point.values, issue))
                rows.append(
                    [
                        self._colored_group_name(test_group.group_id, test_group.group_name),
                        zero_based_index + 1,
                        self._colored_pins(group, pin_ids=test_group.pin_ids),
                        *parameter_values,
                    ]
                )
        self.stress_points.set_rows(["Group", "Point", "Pins", *parameter_names], rows)
        self.stress_points.clearSelection()
        self.stress_points.setCurrentIndex(QModelIndex())
        self._update_power_envelope()

    def _update_power_envelope(self) -> None:
        plan_row = self.plan_list.currentRow()
        if not 0 <= plan_row < len(self._plans):
            self.power_envelope.set_configurations({})
            return

        plan = self._plans[plan_row]
        requests_by_assignment: dict[str, list[Any]] = {}

        state = None
        if plan.device_state_id is not None:
            state = self._device_states_by_id.get(plan.device_state_id)
        if state is None and plan.device_state is not None:
            state = self._device_states_by_name.get(plan.device_state)

        if state is not None:
            for domain in state.power_domains:
                assignment = domain.assignment
                if assignment.upper() in {"GROUND", "FLOATING"}:
                    continue
                requests_by_assignment.setdefault(assignment, [])
                requested = requested_configuration_from_bias(
                    domain.bias,
                    assignment=assignment,
                    label=f"Bias: {domain.name}",
                )
                if requested is not None:
                    requests_by_assignment.setdefault(assignment, []).append(requested)

        if plan.stress_supply is not None:
            assignment = plan.stress_supply.resource
            requests_by_assignment.setdefault(assignment, [])
            for point_index, (values, issue) in enumerate(self._stress_point_contexts):
                tooltip = "\n".join(issue.reasons) if issue is not None else None
                pair = requested_configurations_from_stress(
                    values,
                    assignment=assignment,
                    supported=issue is None,
                    tooltip=tooltip,
                    label=f"Stress point {point_index + 1}",
                    pair_id=f"stress-{point_index}",
                )
                requests_by_assignment.setdefault(assignment, []).extend(pair)
        else:
            # No single stress source can execute the plan. Show the failing requested
            # configurations against each candidate bus independently.
            for point_index, (values, issue) in enumerate(self._stress_point_contexts):
                if issue is None:
                    continue
                reasons_by_assignment: dict[str, list[str]] = {}
                for reason in issue.reasons:
                    assignment, separator, detail = reason.partition(":")
                    if separator and assignment in self._power_resources:
                        reasons_by_assignment.setdefault(assignment, []).append(detail.strip())
                for assignment, reasons in reasons_by_assignment.items():
                    existing = requests_by_assignment.setdefault(assignment, [])
                    pair = requested_configurations_from_stress(
                        values,
                        assignment=assignment,
                        supported=False,
                        tooltip="\n".join(reasons),
                        label=f"Stress point {point_index + 1}",
                        pair_id=f"stress-{point_index}",
                    )
                    if pair:
                        existing.extend(pair)

        self.power_envelope.set_configurations(requests_by_assignment)

    def _set_stress_device_state(self, plan: GeneratedTestPlan) -> None:
        state = None
        if plan.device_state_id is not None:
            state = self._device_states_by_id.get(plan.device_state_id)
        if state is None and plan.device_state is not None:
            state = self._device_states_by_name.get(plan.device_state)

        self.stress_device_state_label.setText(
            f"Device State — {state.name}" if state is not None else "Device State — <none>"
        )
        _set_power_domains_table(self.stress_device_state, state, self._groups_by_name)

    def _colored_group_name(self, group_id: UUID, name: str) -> StyledValue:
        group = self._groups_by_id.get(group_id)
        return StyledValue(name, TYPE_CATEGORY, group.group_type if group is not None else "")

    def _colored_pins(
        self,
        group: GeneratedGroup | None,
        *,
        pin_ids: tuple | None = None,
    ) -> StyledValue:
        if group is None:
            return StyledValue("")
        segments = []
        names = []
        selected_pin_ids = pin_ids if pin_ids is not None else group.pin_ids
        for index, pin_id in enumerate(selected_pin_ids):
            pin = self._pins_by_id.get(pin_id)
            if pin is None:
                continue
            name = pin.name or pin.designator
            names.append(name)
            if index:
                segments.append((", ", None, None))
            segments.append((name, TYPE_CATEGORY, pin.parameters.get("pin_type", "")))
        return StyledValue(", ".join(names), segments=tuple(segments))

    def _clear_details(self) -> None:
        self.groups.set_rows([], [])
        self.stress_points.set_rows([], [])
        self.stress_device_state.set_rows([], [])
        self.stress_device_state_label.setText("Device State")
        self._stress_point_contexts = []
        self.power_envelope.set_configurations({})
        self.summary.clear()


class GenerationViews(QWidget):
    """Generated-data views chosen according to the structure of each collection."""

    TAB_NAMES = ("Pins", "Groups", "Device States", "Hardware Envelopes", "Test Plans")

    def __init__(self, theme: ColorTheme, parent=None) -> None:
        super().__init__(parent)
        self.theme = theme
        self._snapshot: GenerationSnapshot | None = None
        self.tabs = QTabWidget()
        self.pins = GeneratedItemsTable(theme)
        self.groups = GeneratedItemsTable(theme)
        self.device_states = DeviceStatesView(theme)
        self.hardware_envelopes = PowerEnvelopeComparisonView(theme)
        self.test_plans = TestPlansView(theme)
        self.tabs.addTab(self.pins, "Pins")
        self.tabs.addTab(self.groups, "Groups")
        self.tabs.addTab(self.device_states, "Device States")
        self.tabs.addTab(self.hardware_envelopes, "Hardware Envelopes")
        self.tabs.addTab(self.test_plans, "Test Plans")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.tabs)
        self.theme.changed.connect(self._theme_changed)

    def set_snapshot(self, snapshot: GenerationSnapshot) -> None:
        self._snapshot = snapshot
        self.theme.register_values(TYPE_CATEGORY, [pin.parameters.get("pin_type") for pin in snapshot.pins])
        self.theme.register_values(TYPE_CATEGORY, [group.group_type for group in snapshot.groups])
        self.theme.register_values(
            ASSIGNMENT_CATEGORY,
            [domain.assignment for state in snapshot.device_states for domain in state.power_domains],
        )
        self._set_pins(snapshot.pins)
        self._set_groups(snapshot.groups, snapshot.pins)
        self.device_states.set_states(snapshot.device_states, snapshot.groups)
        self.hardware_envelopes.set_power_resources(snapshot.definition.power_resources or {})
        self.hardware_envelopes.set_requested_configuration(None)
        self.test_plans.set_plans(
            snapshot.test_plans,
            snapshot.groups,
            snapshot.pins,
            snapshot.device_states,
            snapshot.definition.power_resources or {},
        )

    def _theme_changed(self) -> None:
        if self._snapshot is not None:
            self.set_snapshot(self._snapshot)

    def show_collection(self, name: str) -> None:
        try:
            index = self.TAB_NAMES.index(name)
        except ValueError:
            return
        self.tabs.setCurrentIndex(index)

    def _set_pins(self, pins: Sequence[GeneratedPin]) -> None:
        parameter_names = sorted({key for pin in pins for key in pin.parameters})
        headers = ["Designator", "Name", *parameter_names, "ID"]
        rows = []
        for pin in pins:
            pin_type = pin.parameters.get("pin_type", "")
            parameter_values = [
                StyledValue(pin.parameters.get(name), TYPE_CATEGORY, pin_type)
                if name == "pin_type"
                else pin.parameters.get(name)
                for name in parameter_names
            ]
            rows.append(
                [
                    StyledValue(pin.designator, TYPE_CATEGORY, pin_type),
                    StyledValue(pin.name, TYPE_CATEGORY, pin_type),
                    *parameter_values,
                    pin.id,
                ]
            )
        self.pins.set_rows(headers, rows)

    def _set_groups(self, groups: Sequence[GeneratedGroup], pins: Sequence[GeneratedPin]) -> None:
        parameter_names = sorted({key for group in groups for key in group.parameters})
        pins_by_id = {pin.id: pin for pin in pins}
        headers = ["Name", "Type", "Pins", "Pin Count", "Bias", *parameter_names, "Rule", "ID"]
        rows = []
        for group in groups:
            pin_segments = []
            names = []
            for index, pin_id in enumerate(group.pin_ids):
                pin = pins_by_id.get(pin_id)
                name = (pin.name or pin.designator) if pin is not None else str(pin_id)
                names.append(name)
                if index:
                    pin_segments.append((", ", None, None))
                pin_segments.append((name, TYPE_CATEGORY, pin.parameters.get("pin_type", "") if pin else ""))
            rows.append(
                [
                    StyledValue(group.name, TYPE_CATEGORY, group.group_type),
                    StyledValue(group.group_type, TYPE_CATEGORY, group.group_type),
                    StyledValue(", ".join(names), segments=tuple(pin_segments)),
                    len(group.pin_ids),
                    group.bias_spec,
                    *(group.parameters.get(name) for name in parameter_names),
                    group.generation_rule_id,
                    group.id,
                ]
            )
        self.groups.set_rows(headers, rows)


# Backwards-compatible name while callers migrate to the structured views.
GenerationTables = GenerationViews


def _display_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, Enum):
        return str(value.value)
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Mapping):
        return json.dumps(value, sort_keys=True, default=str)
    if isinstance(value, (list, tuple, set)):
        return ", ".join(_display_value(item) for item in value)
    return str(value)


def _sort_value(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, (int, float, str)):
        return value
    if isinstance(value, Enum):
        return value.value
    return _display_value(value)
