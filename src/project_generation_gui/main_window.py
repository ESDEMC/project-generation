from html import escape
from pathlib import Path

from qtpy.QtCore import QCoreApplication, QEvent, QEventLoop, Qt, QTimer, QUrl
from qtpy.QtGui import QAction, QDesktopServices
import PySide6QtAds as QtAds

from qtpy.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QFileDialog,
    QInputDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMessageBox,
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
from .preferences import ApplicationPreferences, EditorPreferences, install_application_style
from .session import ProjectSession
from .session_state import SessionState, SessionStore
from .widgets import (
    GenerationViews,
    ObjectTree,
    TextEditor,
    highest_severity,
    severity_icon,
)


class MainWindow(QMainWindow):
    def __init__(
        self,
        *,
        editor_preferences: EditorPreferences | None = None,
        application_preferences: ApplicationPreferences | None = None,
    ) -> None:
        if editor_preferences is None:
            install_application_style()
        super().__init__()
        self.setWindowTitle("Project Generation")
        self.resize(1400, 900)
        self.session = ProjectSession()
        self.color_theme = ColorTheme(self)
        if editor_preferences is None:
            editor_preferences = EditorPreferences(self)
            editor_preferences.apply_theme()
        elif editor_preferences.parent() is None:
            editor_preferences.setParent(self)
        self.editor_preferences = editor_preferences
        self.editor_preferences.changed.connect(self._editor_preferences_changed)
        if application_preferences is None:
            application_preferences = ApplicationPreferences(self)
        elif application_preferences.parent() is None:
            application_preferences.setParent(self)
        self.application_preferences = application_preferences
        self.session_store = SessionStore(self.application_preferences.settings)
        self._session_export_directory: Path | None = None
        self._restoring_session = False
        self._editors: dict[Path, TextEditor] = {}
        self._document_docks: dict[Path, QtAds.CDockWidget] = {}
        self._current_editor: TextEditor | None = None
        self._regenerate_timer = QTimer(self)
        self._regenerate_timer.setSingleShot(True)
        self._regenerate_timer.setInterval(300)
        self._regenerate_timer.timeout.connect(self._auto_regenerate)

        self._layout_settings = self.application_preferences.settings
        self._docking_state_key = "docking/state"

        self.project_tree = QTreeWidget()
        self.project_tree.setColumnCount(2)
        self.project_tree.setHeaderHidden(True)
        self.project_tree.header().setStretchLastSection(False)
        self.project_tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.project_tree.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.project_tree.itemClicked.connect(self._project_item_activated)
        self.project_tree.itemActivated.connect(self._project_item_activated)

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

        self.dock_manager = QtAds.CDockManager(self)
        self._generated_docks: dict[str, QtAds.CDockWidget] = {}

        self.central_workspace = QWidget()
        self.central_dock_manager = QtAds.CDockManager(self.central_workspace)
        central_layout = QVBoxLayout(self.central_workspace)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.addWidget(self.central_dock_manager)

        self.document_workspace_dock = self._configure_dock(QtAds.CDockWidget("Central Workspace"))
        self.document_workspace_dock.setObjectName("CentralWorkspaceDock")
        self.document_workspace_dock.setWidget(self.central_workspace)
        self.dock_manager.setCentralWidget(self.document_workspace_dock)

        self.sessions_view = QTreeWidget()
        self.sessions_view.setColumnCount(3)
        self.sessions_view.setHeaderLabels(["Session", "Definition", "Export Path"])
        self.sessions_view.header().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.sessions_view.header().setSectionResizeMode(1, QHeaderView.Stretch)
        self.sessions_view.header().setSectionResizeMode(2, QHeaderView.Stretch)
        self.sessions_view.itemActivated.connect(self._recent_session_activated)
        self.sessions_dock = self._configure_dock(QtAds.CDockWidget("Recent Sessions"))
        self.sessions_dock.setObjectName("RecentSessionsDock")
        self.sessions_dock.setWidget(self.sessions_view)
        self.central_dock_manager.addDockWidget(
            QtAds.DockWidgetArea.CenterDockWidgetArea,
            self.sessions_dock,
        )

        self.project_dock = self._add_dock(
            "Project", self.project_tree, QtAds.DockWidgetArea.LeftDockWidgetArea
        )

        self.inspector_dock = self._add_dock(
            "Parsed Definition", self.inspector, QtAds.DockWidgetArea.RightDockWidgetArea
        )
        right_area = self.inspector_dock.dockAreaWidget()
        self.parsed_dock = self._add_dock_tab("Parsed Data", self.parsed_view, right_area)
        self.snapshot_dock = self._add_dock_tab("Generation Snapshot", self.snapshot_view, right_area)

        self.problems_dock = self._add_dock(
            "Problems", self.problems_panel, QtAds.DockWidgetArea.BottomDockWidgetArea
        )

        self._default_docking_state = self.dock_manager.saveState()

        self.export_status_label = QLabel()
        self.export_status_label.setTextFormat(Qt.RichText)
        self.export_status_label.setTextInteractionFlags(Qt.TextBrowserInteraction)
        self.export_status_label.setOpenExternalLinks(False)
        self.export_status_label.linkActivated.connect(self._open_export_status_link)
        self.statusBar().addPermanentWidget(self.export_status_label)
        self._set_export_status("")

        self._create_actions()
        self._refresh_recent_sessions()
        QTimer.singleShot(0, self._restore_startup_state)

    @staticmethod
    def _configure_dock(dock: QtAds.CDockWidget) -> QtAds.CDockWidget:
        dock.setFeature(QtAds.CDockWidget.DockWidgetFloatable, False)
        return dock

    def _add_dock(self, title: str, widget: QWidget, area) -> QtAds.CDockWidget:
        dock = self._configure_dock(QtAds.CDockWidget(title))
        dock.setObjectName(title.replace(" ", "") + "Dock")
        dock.setWidget(widget)
        self.dock_manager.addDockWidget(area, dock)
        return dock

    def _add_dock_tab(self, title: str, widget: QWidget, dock_area) -> QtAds.CDockWidget:
        dock = self._configure_dock(QtAds.CDockWidget(title))
        dock.setObjectName(title.replace(" ", "") + "Dock")
        dock.setWidget(widget)
        self.dock_manager.addDockWidgetTabToArea(dock, dock_area)
        return dock

    def _central_dock_area(self, dock: QtAds.CDockWidget | None = None):
        for existing_dock in (*self._document_docks.values(), *self._generated_docks.values()):
            if existing_dock is dock:
                continue
            if existing_dock.dockManager() is not self.central_dock_manager:
                continue
            area = existing_dock.dockAreaWidget()
            if area is not None:
                return area
        return None

    def _add_central_dock(self, dock: QtAds.CDockWidget) -> None:
        dock_area = self._central_dock_area(dock)
        if dock_area is None:
            self.central_dock_manager.addDockWidget(
                QtAds.DockWidgetArea.CenterDockWidgetArea,
                dock,
            )
        else:
            self.central_dock_manager.addDockWidgetTabToArea(dock, dock_area)

    def _show_editor(self, editor: TextEditor) -> QtAds.CDockWidget:
        self.sessions_dock.toggleView(False)
        dock = self._document_docks.get(editor.path)
        if dock is None:
            dock = self._configure_dock(QtAds.CDockWidget(editor.path.name))
            dock.setObjectName(self._document_dock_object_name(editor.path))
            dock.setWidget(editor)
            self._document_docks[editor.path] = dock
            self._add_central_dock(dock)
        else:
            dock.toggleView(True)

        self._current_editor = editor
        editor.setFocus()
        return dock

    @staticmethod
    def _document_dock_object_name(path: Path) -> str:
        safe = "_".join(part for part in path.parts if part).replace(":", "")
        return f"DocumentDock_{safe}"

    def _restore_startup_state(self) -> None:
        self._restore_layout()
        if self.session.definition_document is None and self.application_preferences.restore_last_session:
            state = self.session_store.last()
            if state is not None and Path(state.definition_path).is_file():
                self._restore_session(state)
        if self.session.definition_document is None:
            self._show_recent_sessions_workspace()

    def _capture_session_state(self) -> SessionState | None:
        definition_document = self.session.definition_document
        if definition_document is None:
            return None
        active_paths = {document.path for document in self.session.active_documents()}
        open_documents = tuple(
            str(path)
            for path, dock in self._document_docks.items()
            if path in active_paths and not dock.isClosed()
        )
        generated_views = tuple(
            name for name, dock in self._generated_docks.items() if not dock.isClosed()
        )
        dirty_documents = tuple(
            (str(document.path), document.text)
            for document in self.session.documents.documents()
            if document.dirty
        )
        current_document = None
        if self._current_editor is not None and self._current_editor.path in active_paths:
            current_document = str(self._current_editor.path)
        return SessionState(
            definition_path=str(definition_document.path),
            input_bindings=tuple(
                (directive, str(path)) for directive, path in self.session.input_bindings.items()
            ),
            open_documents=open_documents,
            generated_views=generated_views,
            dirty_documents=dirty_documents,
            current_document=current_document,
            export_directory=(
                str(self._session_export_directory) if self._session_export_directory is not None else None
            ),
        )

    def _save_session_state(self) -> None:
        if self._restoring_session:
            return
        state = self._capture_session_state()
        if state is None:
            return
        self.session_store.save(state, self.central_dock_manager.saveState())
        self._refresh_recent_sessions()

    def _clear_central_session_views(self) -> None:
        remove_dock = getattr(self.central_dock_manager, "removeDockWidget", None)
        for dock in (*self._document_docks.values(), *self._generated_docks.values()):
            if callable(remove_dock):
                remove_dock(dock)
                dock.deleteLater()
            elif not dock.isClosed():
                dock.toggleView(False)
        self._document_docks.clear()
        self._generated_docks.clear()
        self._editors.clear()
        self._current_editor = None
        self.sessions_dock.toggleView(False)

    def _restore_session(self, state: SessionState) -> None:
        definition_path = Path(state.definition_path)
        if not definition_path.is_file():
            self.statusBar().showMessage(f"Session file no longer exists: {definition_path}")
            self._refresh_recent_sessions()
            return
        self._save_session_state()
        self._restoring_session = True
        try:
            self._clear_central_session_views()
            self.session.open_definition(definition_path)
            dirty_documents = {Path(path).resolve(): text for path, text in state.dirty_documents}
            if self.session.definition_document.path in dirty_documents:
                self.session.definition_document.text = dirty_documents[
                    self.session.definition_document.path
                ]
                self.session.regenerate(report_missing_inputs=False)

            valid_directives = set(self.session.input_directives())
            for directive, raw_path in state.input_bindings:
                input_path = Path(raw_path)
                if directive not in valid_directives or not input_path.is_file():
                    continue
                resolved = input_path.resolve()
                self.session.input_bindings[directive] = resolved
                self.session.documents.open(resolved)

            self.session.regenerate(report_missing_inputs=False)
            for path, text in dirty_documents.items():
                document = self.session.documents.get(path)
                if document is not None:
                    document.text = text
            self.session.regenerate(report_missing_inputs=False)
            self._session_export_directory = (
                Path(state.export_directory) if state.export_directory else None
            )
            self._sync_documents()

            for raw_path in state.open_documents:
                document = self.session.documents.get(Path(raw_path))
                if document is not None:
                    self._show_editor(self._ensure_editor(document))
            if not state.open_documents and self.session.definition_document is not None:
                self._show_editor(self._ensure_editor(self.session.definition_document))

            for collection in state.generated_views:
                self._show_generated_items(collection)

            central_state = self.session_store.central_state(definition_path)
            if central_state is not None:
                self.central_dock_manager.restoreState(central_state)

            if state.current_document:
                editor = self._editors.get(Path(state.current_document).resolve())
                if editor is not None:
                    self._show_editor(editor)
            self._refresh_views()
        finally:
            self._restoring_session = False
        self._save_session_state()

    def _show_recent_sessions_workspace(self) -> None:
        self._refresh_recent_sessions()
        self.sessions_dock.toggleView(True)

    def _refresh_recent_sessions(self) -> None:
        states = self.session_store.recent()
        if hasattr(self, "sessions_view"):
            self.sessions_view.clear()
            for state in states:
                definition_path = Path(state.definition_path)
                item = QTreeWidgetItem(
                    [
                        definition_path.stem,
                        str(definition_path),
                        state.export_directory or "",
                    ]
                )
                item.setData(0, Qt.UserRole, state.definition_path)
                if not definition_path.is_file():
                    item.setDisabled(True)
                self.sessions_view.addTopLevelItem(item)
        if hasattr(self, "recent_sessions_menu"):
            self.recent_sessions_menu.clear()
            available = [state for state in states if Path(state.definition_path).is_file()]
            if not available:
                action = self.recent_sessions_menu.addAction("No Recent Sessions")
                action.setEnabled(False)
                return
            for state in available:
                path = Path(state.definition_path)
                action = self.recent_sessions_menu.addAction(f"{path.name} — {path.parent}")
                action.setToolTip(str(path))
                action.triggered.connect(
                    lambda _checked=False, session_state=state: self._restore_session(session_state)
                )
            self.recent_sessions_menu.addSeparator()
            clear_action = self.recent_sessions_menu.addAction("Clear Recent Sessions")
            clear_action.triggered.connect(self._clear_recent_sessions)

    def _clear_recent_sessions(self) -> None:
        self.session_store.clear_recent()
        self._refresh_recent_sessions()

    def _recent_session_activated(self, item: QTreeWidgetItem, _column: int = 0) -> None:
        path = item.data(0, Qt.UserRole)
        if path:
            state = self.session_store.state_for(path)
            if state is not None:
                self._restore_session(state)

    def _restore_layout(self) -> None:
        geometry = self._layout_settings.value("window/geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)

        state = self._layout_settings.value(self._docking_state_key)
        if state is not None:
            self.dock_manager.restoreState(state)

    def _save_layout(self) -> None:
        self._layout_settings.setValue("window/geometry", self.saveGeometry())
        self._layout_settings.setValue(self._docking_state_key, self.dock_manager.saveState())
        self._layout_settings.sync()

    def _reset_layout(self) -> None:
        self.dock_manager.restoreState(self._default_docking_state)
        self._layout_settings.remove(self._docking_state_key)
        self._layout_settings.sync()

    def closeEvent(self, event) -> None:
        self._save_session_state()
        self._save_layout()
        super().closeEvent(event)

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

        self.export_action = QAction("Export Project…", self)
        self.export_action.triggered.connect(lambda _checked=False: self.export_project_dialog())

        settings_action = QAction("Settings…", self)
        settings_action.triggered.connect(lambda _checked=False: self.open_settings())

        file_menu = self.menuBar().addMenu("File")
        file_menu.addAction(open_action)
        self.recent_sessions_menu = file_menu.addMenu("Recent Sessions")
        file_menu.addAction(input_action)
        file_menu.addSeparator()
        file_menu.addAction(save_action)
        file_menu.addAction(save_all_action)
        generate_menu = self.menuBar().addMenu("Generate")
        generate_menu.addAction(regenerate_action)
        generate_menu.addAction(self.export_action)

        tools_menu = self.menuBar().addMenu("Tools")
        tools_menu.addAction(settings_action)

        self.view_menu = self.menuBar().addMenu("View")
        self.reset_layout_action = QAction("Reset Layout", self)
        self.reset_layout_action.triggered.connect(self._reset_layout)
        self.view_menu.addAction(self.reset_layout_action)
        self.view_menu.addSeparator()

        self.panels_menu = self.view_menu.addMenu("Panels")
        for dock in (
            self.project_dock,
            self.inspector_dock,
            self.problems_dock,
            self.parsed_dock,
            self.snapshot_dock,
        ):
            self.panels_menu.addAction(dock.toggleViewAction())

        toolbar = self.addToolBar("Main")
        toolbar.addAction(open_action)
        toolbar.addAction(save_action)
        toolbar.addAction(regenerate_action)
        toolbar.addAction(self.export_action)
        toolbar.addSeparator()
        self.overwrite_existing_checkbox = QCheckBox("Overwrite existing project")
        toolbar.addWidget(self.overwrite_existing_checkbox)

    def export_project_dialog(self) -> None:
        if self.session.definition_document is None:
            self.statusBar().showMessage("Open a generation definition before exporting")
            return
        start_path = self._session_export_directory or self.application_preferences.default_export_path
        if not start_path.exists():
            start_path = self.session.definition_document.path.parent
        output_directory = QFileDialog.getExistingDirectory(self, "Export Project", str(start_path))
        if not output_directory:
            return
        self._session_export_directory = Path(output_directory).resolve()
        self._save_session_state()

        try:
            project_directory = self.session.export_project_directory(output_directory)
        except Exception:
            self._refresh_views()
            self.problems_dock.toggleView(True)
            self._set_export_status("Export failed")
            self.statusBar().showMessage("Export failed — see Problems")
            return

        overwrite = self.overwrite_existing_checkbox.isChecked()
        if project_directory.exists() and not overwrite:
            answer = QMessageBox.question(
                self,
                "Overwrite Existing Project?",
                f'The project already exists:\n{project_directory}\n\nOverwrite everything in this project?',
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                self._set_export_status("Export cancelled")
                self.statusBar().showMessage("Export cancelled")
                return
            overwrite = True

        self._set_export_status("Exporting…")
        self.statusBar().showMessage("Exporting…")
        self.export_action.setEnabled(False)
        QCoreApplication.processEvents(QEventLoop.ExcludeUserInputEvents)
        try:
            project_path = self.session.export_project(output_directory, overwrite=overwrite)
        except Exception:
            self._refresh_views()
            self.problems_dock.toggleView(True)
            self._set_export_status("Export failed")
            self.statusBar().showMessage("Export failed — see Problems")
            return
        finally:
            self.export_action.setEnabled(True)

        self._refresh_views()
        export_folder = project_path.parent
        self._set_export_status(
            f'Exported: <a href="{QUrl.fromLocalFile(str(export_folder)).toString()}">{escape(str(export_folder))}</a>'
        )
        self.statusBar().showMessage(f"Exported project to {project_path}")
        self._save_session_state()
        if self.application_preferences.open_folder_after_export:
            self._open_folder(export_folder)

    def _set_export_status(self, text: str) -> None:
        self.export_status_label.setText(text)
        self.export_status_label.setVisible(bool(text))

    def _open_export_status_link(self, link: str) -> None:
        QDesktopServices.openUrl(QUrl(link))

    def _open_folder(self, path: Path) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def open_settings(self) -> None:
        dialog = ColorSettingsDialog(
            self.color_theme,
            self,
            editor_preferences=self.editor_preferences,
            application_preferences=self.application_preferences,
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
        path, _ = QFileDialog.getOpenFileName(
            self,
            f"Select input for {{{directive}}}",
            start_directory,
            "All files (*)",
        )
        if not path:
            return
        self.session.set_input_file(directive, Path(path))
        self._sync_documents()
        self._refresh_views()
        self._save_session_state()

    def open_definition(self, path: Path) -> None:
        resolved = path.resolve()
        saved_state = self.session_store.state_for(resolved)
        if saved_state is not None:
            self._restore_session(saved_state)
            return
        self._save_session_state()
        self._clear_central_session_views()
        self.session.open_definition(resolved)
        self._session_export_directory = None
        self._sync_documents()
        if self.session.definition_document is not None:
            self._show_editor(self._ensure_editor(self.session.definition_document))
        self._refresh_views()
        self._save_session_state()

    def _sync_documents(self) -> None:
        for document in self.session.active_documents():
            self._ensure_editor(document)
        self._rebuild_project_tree()

    def _ensure_editor(self, document: TextDocument) -> TextEditor:
        editor = self._editors.get(document.path)
        if editor is not None:
            if editor.toPlainText() != document.text:
                editor.blockSignals(True)
                editor.setPlainText(document.text)
                editor.blockSignals(False)
            return editor
        editor = TextEditor(document.path, document.text)
        editor.set_font_size(self.editor_preferences.font_size)
        editor.document_text_changed.connect(lambda text, path=document.path: self._document_changed(path, text))
        editor.installEventFilter(self)
        self._editors[document.path] = editor
        return editor

    def _document_changed(self, path: Path, text: str) -> None:
        self.session.update_document(path, text)
        self._update_tab_titles()
        self._regenerate_timer.start()

    def _auto_regenerate(self) -> None:
        self.session.regenerate(report_missing_inputs=False)
        self._sync_documents()
        self._refresh_views()
        self._save_session_state()

    def _regenerate(self) -> None:
        self.session.regenerate(report_missing_inputs=True)
        self._sync_documents()
        self._refresh_views()
        self._save_session_state()

    def save_current(self) -> None:
        if self._current_editor is not None:
            self.session.save(self._current_editor.path)
            self._update_tab_titles()
            self._save_session_state()

    def save_all(self) -> None:
        self.session.save_all()
        self._update_tab_titles()
        self._save_session_state()

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
            values = (diagnostic.severity, diagnostic.code, diagnostic.location, diagnostic.message)
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 0:
                    icon = severity_icon(self, diagnostic.severity)
                    if icon is not None:
                        item.setIcon(icon)
                self.problems.setItem(row, column, item)
        self.problems.resizeColumnsToContents()

    def _rebuild_project_tree(self) -> None:
        self.project_tree.clear()
        if self.session.definition_document is None:
            return

        definition_document = self.session.definition_document
        root = QTreeWidgetItem([self._document_display_name(definition_document)])
        root.setData(0, Qt.UserRole, ("document", str(definition_document.path)))
        self._apply_document_item_font(root, definition_document)
        definition_severity = self._definition_diagnostic_severity()
        if definition_severity is not None:
            root.setIcon(0, severity_icon(self, definition_severity))
        self.project_tree.addTopLevelItem(root)

        inputs = QTreeWidgetItem(["Input Files"])
        root.addChild(inputs)
        for directive in self.session.input_directives():
            path = self.session.input_bindings.get(directive)
            item = QTreeWidgetItem()
            item.setData(0, Qt.UserRole, ("input", directive))
            self._update_input_file_item(item, directive, path)
            severity = self._severity_for_location_token(f"inputs.{directive}")
            if severity is not None:
                item.setData(0, Qt.DecorationRole, severity_icon(self, severity))
            inputs.addChild(item)
            self.project_tree.setItemWidget(item, 1, self._input_file_browse_button(directive))

        sources = QTreeWidgetItem(["Referenced Files"])
        root.addChild(sources)
        for document in self.session.referenced_documents():
            item = QTreeWidgetItem([self._document_display_name(document)])
            item.setToolTip(0, str(document.path))
            item.setData(0, Qt.UserRole, ("document", str(document.path)))
            self._apply_document_item_font(item, document)
            severity = self._severity_for_document(document)
            if severity is not None:
                item.setIcon(0, severity_icon(self, severity))
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

            generated = QTreeWidgetItem(["Generated"])
            generated.setData(0, Qt.UserRole, ("generated-root", ""))
            root.addChild(generated)

            for name, stage_name, count in (
                ("Pins", "pins", len(snapshot.pins)),
                ("Pin Map", "pin_map", len(getattr(snapshot, "pin_map", ()))),
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

                item = QTreeWidgetItem([f"{name} ({count}){suffix}"])
                tooltip_parts: list[str] = []
                severities: list[object] = []
                if stage is not None and stage.diagnostic is not None:
                    tooltip_parts.append(stage.diagnostic.format())
                    severities.append(stage.diagnostic.severity)
                elif stage is not None and stage.status.value == "failed":
                    severities.append("error")

                if stage_name is not None:
                    matching = [
                        diagnostic
                        for diagnostic in self.session.diagnostics
                        if self._location_matches_stage(str(diagnostic.location), stage_name)
                    ]
                    severities.extend(diagnostic.severity for diagnostic in matching)

                if stage_name == "test_plans" and hardware_issue_plans:
                    severities.append("warning")
                    tooltip_parts.append(hardware_issue_text)

                severity = highest_severity(severities)
                if severity is not None:
                    item.setIcon(0, severity_icon(self, severity))
                if tooltip_parts:
                    item.setToolTip(0, "\n\n".join(tooltip_parts))
                item.setData(0, Qt.UserRole, ("generated", name))
                generated.addChild(item)
            generated.setExpanded(True)
        root.setExpanded(True)
        inputs.setExpanded(True)
        sources.setExpanded(True)

    def _input_file_browse_button(self, directive: str) -> QPushButton:
        browse = QPushButton("Browse…", self.project_tree)
        browse.setObjectName(f"inputFileBrowseButton_{directive}")
        browse.setToolTip(f"Select a file for {{{directive}}}")
        browse.setFlat(True)
        browse.clicked.connect(
            lambda _checked=False, input_directive=directive: self.set_input_file_dialog(
                directive=input_directive
            )
        )
        return browse

    def _update_input_file_item(
        self,
        item: QTreeWidgetItem,
        directive: str,
        path: Path | None,
    ) -> None:
        document = self.session.documents.get(path) if path is not None else None
        dirty = bool(document and document.dirty)
        if path is None:
            item.setText(0, f"{directive}: <not set>")
            item.setToolTip(0, f"No file is set for {{{directive}}}")
        else:
            item.setText(0, f"{directive}: {path.name}{'*' if dirty else ''}")
            item.setToolTip(0, str(path))
        font = item.font(0)
        font.setItalic(dirty)
        item.setFont(0, font)

    def _project_item_activated(self, item: QTreeWidgetItem, _column: int = 0) -> None:
        value = item.data(0, Qt.UserRole)
        if not value:
            return
        kind, payload = value
        if kind == "generated-root":
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
            self._show_editor(editor)

    def _show_generated_items(self, collection: str | None = None) -> None:
        if collection is None:
            return

        self.sessions_dock.toggleView(False)
        view = self.generation_tables.view(collection)
        if view is None:
            return

        dock = self._generated_docks.get(collection)
        if dock is None:
            dock = self._configure_dock(QtAds.CDockWidget(collection))
            dock.setObjectName("Generated" + collection.replace(" ", "") + "Dock")
            dock.setWidget(view)
            self._add_central_dock(dock)
            self._generated_docks[collection] = dock
            if hasattr(self, "panels_menu"):
                self.panels_menu.addAction(dock.toggleViewAction())

        dock.toggleView(True)
        self._save_session_state()

    def _update_tab_titles(self) -> None:
        for editor in self._editors.values():
            document = self.session.documents.get(editor.path)
            dirty = bool(document and document.dirty)
            dock = self._document_docks.get(editor.path)
            if dock is not None:
                dock.setWindowTitle(editor.path.name + ("*" if dirty else ""))
                tab = dock.tabWidget() if hasattr(dock, "tabWidget") else None
                if tab is not None:
                    font = tab.font()
                    font.setItalic(dirty)
                    tab.setFont(font)
        self._update_document_item_states()

    @staticmethod
    def _document_display_name(document: TextDocument) -> str:
        return document.path.name + ("*" if document.dirty else "")

    @staticmethod
    def _apply_document_item_font(item: QTreeWidgetItem, document: TextDocument) -> None:
        font = item.font(0)
        font.setItalic(document.dirty)
        item.setFont(0, font)

    def _update_document_item_states(self) -> None:
        if self.project_tree.topLevelItemCount() == 0:
            return

        def visit(item: QTreeWidgetItem) -> None:
            value = item.data(0, Qt.UserRole)
            if value:
                kind, payload = value
                if kind == "document":
                    document = self.session.documents.get(Path(payload))
                    if document is not None:
                        item.setText(0, self._document_display_name(document))
                        self._apply_document_item_font(item, document)
                elif kind == "input":
                    path = self.session.input_bindings.get(payload)
                    self._update_input_file_item(item, payload, path)
            for index in range(item.childCount()):
                visit(item.child(index))

        for index in range(self.project_tree.topLevelItemCount()):
            visit(self.project_tree.topLevelItem(index))

    @staticmethod
    def _location_matches_stage(location: str, stage_name: str) -> bool:
        prefixes = (
            stage_name,
            f"generated_project.{stage_name}",
        )
        return any(
            location == prefix
            or location.startswith(prefix + ".")
            or location.startswith(prefix + "[")
            for prefix in prefixes
        )

    def _severity_for_location_token(self, token: str) -> str | None:
        return highest_severity(
            [
                diagnostic.severity
                for diagnostic in self.session.diagnostics
                if token in str(diagnostic.location)
            ]
        )

    def _severity_for_document(self, document: TextDocument) -> str | None:
        return highest_severity(
            [
                diagnostic.severity
                for diagnostic in self.session.diagnostics
                if str(diagnostic.location).startswith(document.path.name)
            ]
        )

    def _definition_diagnostic_severity(self) -> str | None:
        document = self.session.definition_document
        if document is None:
            return None
        severities = []
        for diagnostic in self.session.diagnostics:
            location = str(diagnostic.location)
            if location.startswith(document.path.name):
                severities.append(diagnostic.severity)
                continue
            if diagnostic.code in {"SCHEMA_VALIDATION_ERROR"}:
                severities.append(diagnostic.severity)
        return highest_severity(severities)

    def eventFilter(self, watched, event) -> bool:
        if watched in self._editors.values() and event.type() in (QEvent.FocusIn, QEvent.MouseButtonPress):
            self._current_editor = watched
        return super().eventFilter(watched, event)

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
