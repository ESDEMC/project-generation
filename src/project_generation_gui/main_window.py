from pathlib import Path

from qtpy.QtCore import Qt, QTimer
from qtpy.QtGui import QAction
from qtpy.QtWidgets import (
    QFileDialog,
    QMainWindow,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
    QWidget,
)

from .documents import TextDocument
from .session import ProjectSession
from .widgets import ObjectTree, TextEditor


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Project Generation")
        self.resize(1400, 900)
        self.session = ProjectSession()
        self._editors: dict[Path, TextEditor] = {}
        self._regenerate_timer = QTimer(self)
        self._regenerate_timer.setSingleShot(True)
        self._regenerate_timer.setInterval(300)
        self._regenerate_timer.timeout.connect(self._regenerate)

        self.project_tree = QTreeWidget()
        self.project_tree.setHeaderHidden(True)
        self.project_tree.itemDoubleClicked.connect(self._project_item_activated)

        self.editors = QTabWidget()
        self.editors.setTabsClosable(False)

        self.inspector = ObjectTree()
        self.inspector.setHeaderLabels(["Parsed definition", "Value"])

        upper = QSplitter(Qt.Horizontal)
        upper.addWidget(self.project_tree)
        upper.addWidget(self.editors)
        upper.addWidget(self.inspector)
        upper.setStretchFactor(0, 0)
        upper.setStretchFactor(1, 1)
        upper.setStretchFactor(2, 0)

        self.bottom_tabs = QTabWidget()
        self.problems = QTableWidget(0, 4)
        self.problems.setHorizontalHeaderLabels(["Severity", "Code", "Location", "Message"])
        self.parsed_view = ObjectTree()
        self.snapshot_view = ObjectTree()
        self.bottom_tabs.addTab(self.problems, "Problems")
        self.bottom_tabs.addTab(self.parsed_view, "Parsed Data")
        self.bottom_tabs.addTab(self.snapshot_view, "Generation Snapshot")

        central = QSplitter(Qt.Vertical)
        central.addWidget(upper)
        central.addWidget(self.bottom_tabs)
        central.setStretchFactor(0, 3)
        central.setStretchFactor(1, 2)
        container = QWidget()
        self.setCentralWidget(central)

        self._create_actions()

    def _create_actions(self) -> None:
        open_action = QAction("Open Generation File…", self)
        open_action.setShortcut("Ctrl+O")
        open_action.triggered.connect(self.open_dialog)

        save_action = QAction("Save", self)
        save_action.setShortcut("Ctrl+S")
        save_action.triggered.connect(self.save_current)

        save_all_action = QAction("Save All", self)
        save_all_action.setShortcut("Ctrl+Shift+S")
        save_all_action.triggered.connect(self.save_all)

        regenerate_action = QAction("Regenerate", self)
        regenerate_action.setShortcut("Ctrl+R")
        regenerate_action.triggered.connect(self._regenerate)

        file_menu = self.menuBar().addMenu("File")
        file_menu.addAction(open_action)
        file_menu.addAction(save_action)
        file_menu.addAction(save_all_action)
        generate_menu = self.menuBar().addMenu("Generate")
        generate_menu.addAction(regenerate_action)

        toolbar = self.addToolBar("Main")
        toolbar.addAction(open_action)
        toolbar.addAction(save_action)
        toolbar.addAction(regenerate_action)

    def open_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Generation Definition",
            "",
            "Generation definitions (*.yaml *.yml *.json);;All files (*)",
        )
        if path:
            self.open_definition(Path(path))

    def open_definition(self, path: Path) -> None:
        self.session.open_definition(path)
        self._sync_documents()
        self._refresh_views()

    def _sync_documents(self) -> None:
        for document in self.session.documents.documents():
            self._ensure_editor(document)
        self._rebuild_project_tree()

    def _ensure_editor(self, document: TextDocument) -> TextEditor:
        editor = self._editors.get(document.path)
        if editor is not None:
            return editor
        editor = TextEditor(document.path, document.text)
        editor.document_text_changed.connect(lambda text, path=document.path: self._document_changed(path, text))
        self._editors[document.path] = editor
        self.editors.addTab(editor, document.path.name)
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
        editor = self.editors.currentWidget()
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
            self.snapshot_view.set_value(self.session.snapshot)
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
        root.setData(0, Qt.UserRole, str(self.session.definition_document.path))
        self.project_tree.addTopLevelItem(root)

        sources = QTreeWidgetItem(["Referenced Files"])
        root.addChild(sources)
        for document in self.session.referenced_documents():
            item = QTreeWidgetItem([document.path.name])
            item.setToolTip(0, str(document.path))
            item.setData(0, Qt.UserRole, str(document.path))
            sources.addChild(item)

        if self.session.snapshot is not None:
            generated = QTreeWidgetItem(["Generated"])
            root.addChild(generated)
            snapshot = self.session.snapshot
            for name, count in (
                ("Pins", len(snapshot.pins)),
                ("Groups", len(snapshot.groups)),
                ("Device States", len(snapshot.device_states)),
                ("Test Plans", len(snapshot.test_plans)),
            ):
                generated.addChild(QTreeWidgetItem([f"{name} ({count})"]))
        root.setExpanded(True)
        sources.setExpanded(True)

    def _project_item_activated(self, item: QTreeWidgetItem) -> None:
        value = item.data(0, Qt.UserRole)
        if not value:
            return
        path = Path(value)
        editor = self._editors.get(path)
        if editor is not None:
            self.editors.setCurrentWidget(editor)

    def _update_tab_titles(self) -> None:
        for index in range(self.editors.count()):
            editor = self.editors.widget(index)
            if not isinstance(editor, TextEditor):
                continue
            document = self.session.documents.get(editor.path)
            suffix = " ●" if document and document.dirty else ""
            self.editors.setTabText(index, editor.path.name + suffix)

    def _status_text(self) -> str:
        if self.session.definition_document is None:
            return "No generation definition open"
        if any(item.severity.lower() == "error" for item in self.session.diagnostics):
            return "Working copy has errors — showing the last successful snapshot"
        if self.session.snapshot is None:
            return "Definition parsed; no generation snapshot available"
        snapshot = self.session.snapshot
        return (
            f"Generated from working copy: {len(snapshot.pins)} pins, {len(snapshot.groups)} groups, "
            f"{len(snapshot.device_states)} states, {len(snapshot.test_plans)} test plans"
        )
