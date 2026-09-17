from types import SimpleNamespace

from qtpy.QtCore import Qt
from qtpy.QtWidgets import QToolBar

from project_generation_gui.documents import TextDocument
from project_generation_gui.session import SessionDiagnostic

from project_generation_gui.main_window import MainWindow


def test_generated_items_open_in_central_editor_area(qtbot) -> None:
    window = MainWindow()
    qtbot.addWidget(window)

    window._show_generated_items("Groups")
    assert window.editor_area.current_editor() is window.generation_tables
    assert window.generation_tables.stack.currentIndex() == 1

    window._show_generated_items("Pins")
    assert window.editor_area.current_editor() is window.generation_tables
    assert window.generation_tables.stack.currentIndex() == 0
    assert sum(
        editor is window.generation_tables
        for _group, _index, editor in window.editor_area.iter_editors()
    ) == 1


def test_clear_problems_button_clears_displayed_diagnostics(qtbot) -> None:
    window = MainWindow()
    qtbot.addWidget(window)
    window.session.diagnostics = (
        SessionDiagnostic("error", "TEST_ERROR", "Something failed", "definition"),
    )
    window._refresh_problems()
    assert window.problems.rowCount() == 1

    qtbot.mouseClick(window.clear_problems_button, Qt.LeftButton)

    assert window.session.diagnostics == ()
    assert window.problems.rowCount() == 0


def test_hardware_issues_mark_only_test_plans_tree_item(qtbot, tmp_path) -> None:
    window = MainWindow()
    qtbot.addWidget(window)

    definition_path = tmp_path / "generation.yaml"
    definition_path.write_text("{}", encoding="utf-8")
    window.session.definition_document = TextDocument.load(definition_path)
    issue = SimpleNamespace(reasons=("DC1 voltage limit exceeded",))
    plan = SimpleNamespace(name="Signal I Test", hardware_issues=(issue,))
    window.session.snapshot = SimpleNamespace(
        pins=(),
        groups=(),
        device_states=(),
        test_plans=(plan,),
        definition=SimpleNamespace(power_resources={}),
        stage=lambda _name: None,
    )

    window._rebuild_project_tree()

    root = window.project_tree.topLevelItem(0)
    generated = root.child(2)
    test_plans = generated.child(4)

    assert generated.text(0) == "Generated"
    assert generated.icon(0).isNull()
    assert test_plans.text(0) == "Test Plans (1)"
    assert not test_plans.icon(0).isNull()
    assert "Signal I Test" in test_plans.toolTip(0)
    assert "DC1 voltage limit exceeded" in test_plans.toolTip(0)


def test_input_file_action_is_not_in_main_toolbar(qtbot) -> None:
    window = MainWindow()
    qtbot.addWidget(window)

    toolbars = window.findChildren(QToolBar)
    assert toolbars
    assert "Set Input File…" not in {action.text() for action in toolbars[0].actions()}


def test_input_file_rows_have_browse_button(qtbot, tmp_path) -> None:
    window = MainWindow()
    qtbot.addWidget(window)

    definition_path = tmp_path / "generation.yaml"
    definition_path.write_text(
        "schema_version: 1.0\nproject: {}\nsources: {}\nformat: {}\n",
        encoding="utf-8",
    )
    window.session.definition_document = TextDocument.load(definition_path)
    window.session.input_directives = lambda: ("input_file",)
    window.session.input_bindings = {}

    window._rebuild_project_tree()

    root = window.project_tree.topLevelItem(0)
    inputs = root.child(0)
    item = inputs.child(0)
    row = window.project_tree.itemWidget(item, 0)
    assert row is not None
    browse = row.findChild(type(window.clear_problems_button), "inputFileBrowseButton_input_file")
    assert browse is not None
    assert browse.text() == "Browse…"


def test_problem_rows_use_standard_severity_icons(qtbot) -> None:
    window = MainWindow()
    qtbot.addWidget(window)
    window.session.diagnostics = (
        SessionDiagnostic("warning", "WARN", "Warning", "test_plans.plan"),
        SessionDiagnostic("error", "ERR", "Error", "groups"),
    )

    window._refresh_problems()

    assert not window.problems.item(0, 0).icon().isNull()
    assert not window.problems.item(1, 0).icon().isNull()
    assert window.problems.item(0, 0).icon().cacheKey() != window.problems.item(1, 0).icon().cacheKey()


def test_dirty_document_marks_tab_and_tree_item_with_asterisk_and_italic(qtbot, tmp_path) -> None:
    window = MainWindow()
    qtbot.addWidget(window)

    path = tmp_path / "generation.yaml"
    path.write_text("schema_version: 1.0\n", encoding="utf-8")
    document = TextDocument.load(path)
    window.session.definition_document = document
    window.session.documents._documents[document.path] = document
    editor = window._ensure_editor(document)
    window._rebuild_project_tree()

    document.text += "# changed\n"
    window._update_tab_titles()

    tab_index = window.editor_area._tabs.indexOf(editor)
    root = window.project_tree.topLevelItem(0)
    assert window.editor_area._tabs.tabText(tab_index) == "generation.yaml*"
    assert bool(window.editor_area._tabs.tabBar().tabData(tab_index))
    assert root.text(0) == "generation.yaml*"
    assert root.font(0).italic()
