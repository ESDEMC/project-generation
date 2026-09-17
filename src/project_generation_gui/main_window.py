from pathlib import Path

from qtpy.QtCore import Qt, QTimer
from qtpy.QtGui import QAction, QColor
from qtpy.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QDockWidget,
    QInputDialog,
    QHBoxLayout,
    QMainWindow,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .colors import ColorSettingsDialog, ColorTheme
from .documents import TextDocument
from .preferences import EditorPreferences
from .session import ProjectSession
from .widgets import EditorArea, GenerationViews, ObjectTree, TextEditor


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Project Generation")
        self.resize(1400, 900)
        self.session = ProjectSession()
        self.color_theme = ColorTheme(self)
        self.editor_preferences = EditorPreferences(self)
        self.editor_preferences.apply_theme()
        self.editor_preferences.changed.connect(self._editor_preferences_changed)
        self._editors: dict[Path, TextEditor] = {}
        self._regenerate_timer = QTimer(self)
        self._regenerate_timer.setSingleShot(True)
        self._regenerate_timer.setInterval(300)
        self._regenerate_timer.timeout.connect(self._regenerate)

        self.setDockNestingEnabled(True)

        self.project_tree = QTreeWidget()
        self.project_tree.setHeaderHidden(True)
        self.project_tree.itemClicked.connect(self._project_item_activated)
        self.project_tree.itemActivated.connect(self._project_item_activated)

        self.editor_area = EditorArea()
        self.setCentralWidget(self.editor_area)

        self.inspector = ObjectTree()
        self.inspector.setHeaderLabels(["Parsed definition", "Value"])

        self.problems = QTableWidget(0, 4)
        self.problems.setHorizontalHeaderLabels(["Severity", "Code", "Location", "Message"])
        self.problems.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.problems_panel = QWidget()
        problems_layout = QVBoxLayout(self.problems_panel)
        problems_layout.setContentsMargins(0, 0, 0, 0)
        problems_toolbar = QHBoxLayout()
        problems_toolbar.addStretch(1)
        self.clear_problems_button = QPushButton("Clear")
        self.clear_problems_button.setToolTip("Clear the current diagnostics until the next regeneration")
        self.clear_problems_button.clicked.connect(self._clear_problems)
        problems_toolbar.addWidget(self.clear_problems_button)
        problems_layout.addLayout(problems_toolbar)
        problems_layout.addWidget(self.problems, 1)
        self.parsed_view = ObjectTree()
        self.generation_tables = GenerationViews(self.color_theme)
        self.snapshot_view = ObjectTree()

        self.project_dock = self._add_dock("Project", self.project_tree, Qt.LeftDockWidgetArea)
        self.inspector_dock = self._add_dock("Parsed Definition", self.inspector, Qt.RightDockWidgetArea)
        self.problems_dock = self._add_dock("Problems", self.problems_panel, Qt.BottomDockWidgetArea)
        self.parsed_dock = self._add_dock("Parsed Data", self.parsed_view, Qt.BottomDockWidgetArea)
        self.snapshot_dock = self._add_dock("Generation Snapshot", self.snapshot_view, Qt.BottomDockWidgetArea)

        self.tabifyDockWidget(self.problems_dock, self.parsed_dock)
        self.tabifyDockWidget(self.problems_dock, self.snapshot_dock)
        self.problems_dock.raise_()

        self._create_actions()
        QTimer.singleShot(0, self._collapse_bottom_docks)

    def _collapse_bottom_docks(self) -> None:
        self.problems_dock.raise_()
        for dock in (self.problems_dock, self.parsed_dock, self.snapshot_dock):
            dock.hide()

    def _add_dock(self, title: str, widget: QWidget, area: int) -> QDockWidget:
        dock = QDockWidget(title, self)
        dock.setObjectName(title.replace(" ", "") + "Dock")
        dock.setWidget(widget)
        self.addDockWidget(area, dock)
        return dock

    def _create_actions(self) -> None:
        open_action = QAction("Open Generation File…", self)
        open_action.setShortcut("Ctrl+O")
        open_action.triggered.connect(self.open_dialog)

        input_action = QAction("Set Input File…", self)
        input_action.triggered.connect(lambda _checked=False: self.set_input_file_dialog())

        save_action = QAction("Save", self)
        save_action.setShortcut("Ctrl+S")
        save_action.triggered.connect(self.save_current)

        save_all_action = QAction("Save All", self)
        save_all_action.setShortcut("Ctrl+Shift+S")
        save_all_action.triggered.connect(self.save_all)

        regenerate_action = QAction("Regenerate", self)
        regenerate_action.setShortcut("Ctrl+R")
        regenerate_action.triggered.connect(self._regenerate)

        export_action = QAction("Export Project…", self)
        export_action.triggered.connect(lambda _checked=False: self.export_project_dialog())

        settings_action = QAction("Settings…", self)
        settings_action.triggered.connect(lambda _checked=False: self.open_settings())

        file_menu = self.menuBar().addMenu("File")
        file_menu.addAction(open_action)
        file_menu.addAction(input_action)
        file_menu.addSeparator()
        file_menu.addAction(save_action)
        file_menu.addAction(save_all_action)
        generate_menu = self.menuBar().addMenu("Generate")
        generate_menu.addAction(regenerate_action)
        generate_menu.addAction(export_action)

        tools_menu = self.menuBar().addMenu("Tools")
        tools_menu.addAction(settings_action)

        view_menu = self.menuBar().addMenu("View")
        for dock in (
            self.project_dock,
            self.inspector_dock,
            self.problems_dock,
            self.parsed_dock,
            self.snapshot_dock,
        ):
            view_menu.addAction(dock.toggleViewAction())

        toolbar = self.addToolBar("Main")
        toolbar.addAction(open_action)
        toolbar.addAction(input_action)
        toolbar.addAction(save_action)
        toolbar.addAction(regenerate_action)
        toolbar.addAction(export_action)

    def export_project_dialog(self) -> None:
        if self.session.definition_document is None:
            self.statusBar().showMessage("Open a generation definition before exporting")
            return
        start = str(self.session.definition_document.path.parent)
        output_directory = QFileDialog.getExistingDirectory(self, "Export Project", start)
        if not output_directory:
            return
        try:
            project_path = self.session.export_project(output_directory)
        except Exception:
            self._refresh_views()
            self.problems_dock.show()
            self.problems_dock.raise_()
            self.statusBar().showMessage("Export failed — see Problems")
            return
        self._refresh_views()
        self.statusBar().showMessage(f"Exported project to {project_path}")

    def open_settings(self) -> None:
        dialog = ColorSettingsDialog(
            self.color_theme, self, editor_preferences=self.editor_preferences
        )
        dialog.exec()

    def open_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Generation Definition",
            "",
            "Generation definitions (*.yaml *.yml *.json);;All files (*)",
        )
        if path:
            self.open_definition(Path(path))

    def set_input_file_dialog(self, *, directive: str | None = None) -> None:
        directives = self.session.input_directives()
        if directive is None:
            if not directives:
                self.statusBar().showMessage("The current definition does not declare any input-file directives")
                return
            directive, accepted = QInputDialog.getItem(
                self,
                "Set Input File",
                "Directive",
                list(directives),
                editable=False,
            )
            if not accepted:
                return

        current = self.session.input_bindings.get(directive)
        start_directory = str(current.parent if current is not None else self.session.definition_document.path.parent)
        path, _ = QFileDialog.getOpenFileName(self, f"Select input for {{{directive}}}", start_directory, "All files (*)")
        if not path:
            return
        self.session.set_input_file(directive, Path(path))
        self._sync_documents()
        self._refresh_views()

    def open_definition(self, path: Path) -> None:
        self.session.open_definition(path)
        self._sync_documents()
        self._refresh_views()
        if self.session.snapshot is not None:
            self._show_generated_items()

    def _sync_documents(self) -> None:
        for document in self.session.active_documents():
            self._ensure_editor(document)
        self._rebuild_project_tree()

    def _ensure_editor(self, document: TextDocument) -> TextEditor:
        editor = self._editors.get(document.path)
        if editor is not None:
            return editor
        editor = TextEditor(document.path, document.text)
        editor.set_font_size(self.editor_preferences.font_size)
        editor.document_text_changed.connect(lambda text, path=document.path: self._document_changed(path, text))
        self._editors[document.path] = editor
        self.editor_area.add_editor(editor, document.path.name)
        return editor

    def _document_changed(self, path: Path, text: str) -> None:
        self.session.update_document(path, text)
        self._update_tab_titles()
        self._regenerate_timer.start()

    def _regenerate(self) -> None:
        self.session.regenerate()
        self._sync_documents()
        self._refresh_views()

    def save_current(self) -> None:
        editor = self.editor_area.current_editor()
        if isinstance(editor, TextEditor):
            self.session.save(editor.path)
            self._update_tab_titles()

    def save_all(self) -> None:
        self.session.save_all()
        self._update_tab_titles()

    def _refresh_views(self) -> None:
        self._refresh_problems()
        if self.session.definition is not None:
            self.parsed_view.set_value(self.session.definition)
            self.inspector.set_value(self.session.definition)
        if self.session.snapshot is not None:
            self.generation_tables.set_snapshot(self.session.snapshot)
            self.snapshot_view.set_value(self.session.snapshot)
        self.statusBar().showMessage(self._status_text())

    def _clear_problems(self) -> None:
        self.session.clear_diagnostics()
        self._refresh_problems()
        self.statusBar().showMessage(self._status_text())

    def _refresh_problems(self) -> None:
        diagnostics = self.session.diagnostics
        self.problems.setRowCount(len(diagnostics))
        for row, diagnostic in enumerate(diagnostics):
            for column, value in enumerate((diagnostic.severity, diagnostic.code, diagnostic.location, diagnostic.message)):
                self.problems.setItem(row, column, QTableWidgetItem(value))
        self.problems.resizeColumnsToContents()

    def _rebuild_project_tree(self) -> None:
        self.project_tree.clear()
        if self.session.definition_document is None:
            return
        root = QTreeWidgetItem([self.session.definition_document.path.name])
        root.setData(0, Qt.UserRole, ("document", str(self.session.definition_document.path)))
        self.project_tree.addTopLevelItem(root)

        inputs = QTreeWidgetItem(["Input Files"])
        root.addChild(inputs)
        for directive in self.session.input_directives():
            path = self.session.input_bindings.get(directive)
            label = f"{directive}: {path.name}" if path is not None else f"{directive}: <not set>"
            item = QTreeWidgetItem([label])
            item.setToolTip(0, str(path) if path is not None else f"Format directive {{{directive}}}")
            item.setData(0, Qt.UserRole, ("input", directive))
            inputs.addChild(item)

        sources = QTreeWidgetItem(["Referenced Files"])
        root.addChild(sources)
        for document in self.session.referenced_documents():
            item = QTreeWidgetItem([document.path.name])
            item.setToolTip(0, str(document.path))
            item.setData(0, Qt.UserRole, ("document", str(document.path)))
            sources.addChild(item)

        if self.session.snapshot is not None:
            snapshot = self.session.snapshot
            hardware_issue_plans = tuple(plan for plan in snapshot.test_plans if plan.hardware_issues)
            hardware_issue_text = "\n\n".join(
                f"{plan.name}:\n"
                + "\n".join(
                    reason
                    for issue in plan.hardware_issues
                    for reason in issue.reasons
                )
                for plan in hardware_issue_plans
            )

            generated_label = "Generated"
            if hardware_issue_plans:
                generated_label += " — warnings"
            generated = QTreeWidgetItem([generated_label])
            if hardware_issue_plans:
                generated.setForeground(0, QColor("#EF5350"))
                generated.setToolTip(0, hardware_issue_text)
            generated.setData(0, Qt.UserRole, ("generated-root", ""))
            root.addChild(generated)

            for name, stage_name, count in (
                ("Pins", "pins", len(snapshot.pins)),
                ("Groups", "groups", len(snapshot.groups)),
                ("Device States", "device_states", len(snapshot.device_states)),
                (
                    "Hardware Envelopes",
                    None,
                    len(snapshot.definition.power_resources or {}),
                ),
                ("Test Plans", "test_plans", len(snapshot.test_plans)),
            ):
                stage = snapshot.stage(stage_name) if stage_name is not None else None
                suffix = ""
                if stage is not None and stage.status.value != "complete":
                    suffix = f" — {stage.status.value.replace('_', ' ')}"
                elif stage_name == "test_plans" and hardware_issue_plans:
                    suffix = " — warnings"

                item = QTreeWidgetItem([f"{name} ({count}){suffix}"])
                tooltip_parts: list[str] = []
                if stage is not None and stage.diagnostic is not None:
                    tooltip_parts.append(stage.diagnostic.format())
                if stage_name == "test_plans" and hardware_issue_plans:
                    item.setForeground(0, QColor("#EF5350"))
                    tooltip_parts.append(hardware_issue_text)
                if tooltip_parts:
                    item.setToolTip(0, "\n\n".join(tooltip_parts))
                item.setData(0, Qt.UserRole, ("generated", name))
                generated.addChild(item)
            generated.setExpanded(True)
        root.setExpanded(True)
        inputs.setExpanded(True)
        sources.setExpanded(True)

    def _project_item_activated(self, item: QTreeWidgetItem, _column: int = 0) -> None:
        value = item.data(0, Qt.UserRole)
        if not value:
            return
        kind, payload = value
        if kind == "generated-root":
            self._show_generated_items()
            return
        if kind == "generated":
            self._show_generated_items(payload)
            return
        if kind == "input":
            path = self.session.input_bindings.get(payload)
            if path is None:
                self.set_input_file_dialog(directive=payload)
                return
        else:
            path = Path(payload)
        editor = self._editors.get(path)
        if editor is not None:
            if not self.editor_area.contains_editor(editor):
                document = self.session.documents.get(path)
                suffix = " ●" if document and document.dirty else ""
                self.editor_area.add_editor(editor, editor.path.name + suffix)
            else:
                self.editor_area.set_current_editor(editor)


    def _show_generated_items(self, collection: str | None = None) -> None:
        if collection is not None:
            self.generation_tables.show_collection(collection)
        if not any(editor is self.generation_tables for _group, _index, editor in self.editor_area.iter_editors()):
            self.editor_area.add_editor(self.generation_tables, "Generated Items")
        else:
            self.editor_area.set_current_editor(self.generation_tables)

    def _update_tab_titles(self) -> None:
        for editor in self._editors.values():
            document = self.session.documents.get(editor.path)
            suffix = " ●" if document and document.dirty else ""
            self.editor_area.set_editor_title(editor, editor.path.name + suffix)

    def _editor_preferences_changed(self) -> None:
        for editor in self._editors.values():
            editor.set_font_size(self.editor_preferences.font_size)

    def _status_text(self) -> str:
        if self.session.definition_document is None:
            return "No generation definition open"
        if self.session.snapshot is None:
            if any(item.severity.lower() == "error" for item in self.session.diagnostics):
                return "Working copy has errors — no generation snapshot available"
            return "Definition parsed; no generation snapshot available"
        snapshot = self.session.snapshot
        failed = [stage.name for stage in snapshot.stages if stage.status.value == "failed"]
        prefix = f"Best effort stopped at {failed[0]}: " if failed else "Generated from working copy: "
        return (
            f"{prefix}{len(snapshot.pins)} pins, {len(snapshot.groups)} groups, "
            f"{len(snapshot.device_states)} states, {len(snapshot.test_plans)} test plans"
        )
