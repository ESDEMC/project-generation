from types import SimpleNamespace

from qtpy.QtCore import Qt
from qtpy.QtWidgets import QDockWidget

from project_generation_gui.documents import TextDocument
from project_generation_gui.session import SessionDiagnostic

from project_generation_gui.main_window import MainWindow


def test_generated_items_open_in_central_editor_area(qtbot) -> None:
    window = MainWindow()
    qtbot.addWidget(window)

    assert all(dock.windowTitle() != "Generated Items" for dock in window.findChildren(QDockWidget))

    window._show_generated_items("Groups")
    assert window.editor_area.current_editor() is window.generation_tables
    assert window.generation_tables.tabs.currentIndex() == 1

    window._show_generated_items("Pins")
    assert window.editor_area.current_editor() is window.generation_tables
    assert window.generation_tables.tabs.currentIndex() == 0
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


def test_hardware_issues_propagate_to_test_plans_and_generated_nodes(qtbot, tmp_path) -> None:
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
        stage=lambda _name: None,
    )

    window._rebuild_project_tree()

    root = window.project_tree.topLevelItem(0)
    generated = root.child(2)
    test_plans = generated.child(3)

    assert generated.text(0) == "Generated — warnings"
    assert test_plans.text(0) == "Test Plans (1) — warnings"
    assert generated.foreground(0).color().name().upper() == "#EF5350"
    assert test_plans.foreground(0).color().name().upper() == "#EF5350"
    assert "Signal I Test" in test_plans.toolTip(0)
    assert "DC1 voltage limit exceeded" in test_plans.toolTip(0)
