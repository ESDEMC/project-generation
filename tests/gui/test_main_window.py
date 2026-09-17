from types import SimpleNamespace

from qtpy.QtCore import QSettings, Qt
from qtpy.QtWidgets import QMessageBox, QToolBar
import PySide6QtAds as QtAds

from project_generation_gui.documents import TextDocument
from project_generation_gui.session import SessionDiagnostic

from project_generation_gui.main_window import MainWindow
from project_generation_gui.preferences import ApplicationPreferences


def test_generated_items_share_central_ads_area(qtbot) -> None:
    window = MainWindow()
    qtbot.addWidget(window)

    window._show_generated_items("Groups")
    groups_dock = window._generated_docks["Groups"]
    assert groups_dock.dockManager() is window.central_dock_manager

    window._show_generated_items("Pins")
    pins_dock = window._generated_docks["Pins"]
    assert pins_dock.dockManager() is window.central_dock_manager
    assert pins_dock is not groups_dock
    assert groups_dock.dockAreaWidget() is pins_dock.dockAreaWidget()
    assert groups_dock.dockAreaWidget() is window._central_dock_area()


def test_central_area_is_recreated_after_last_central_dock_is_closed(qtbot) -> None:
    window = MainWindow()
    qtbot.addWidget(window)

    window._show_generated_items("Groups")
    groups_dock = window._generated_docks["Groups"]
    groups_dock.toggleView(False)

    window._show_generated_items("Pins")
    pins_dock = window._generated_docks["Pins"]

    assert pins_dock.dockManager() is window.central_dock_manager
    assert pins_dock.dockAreaWidget() is not None


def test_document_is_created_without_docking_until_opened(qtbot, tmp_path) -> None:
    window = MainWindow()
    qtbot.addWidget(window)

    path = tmp_path / "generation.yaml"
    path.write_text("schema_version: 1.0\n", encoding="utf-8")
    document = TextDocument.load(path)
    window.session.definition_document = document
    window.session.documents._documents[document.path] = document

    editor = window._ensure_editor(document)

    assert document.path not in window._document_docks
    window._show_editor(editor)
    document_dock = window._document_docks[document.path]
    assert document_dock.dockManager() is window.central_dock_manager
    assert document_dock.dockAreaWidget() is window._central_dock_area()


def test_documents_and_generated_views_share_the_same_central_area(qtbot, tmp_path) -> None:
    window = MainWindow()
    qtbot.addWidget(window)

    path = tmp_path / "generation.yaml"
    path.write_text("schema_version: 1.0\n", encoding="utf-8")
    document = TextDocument.load(path)
    window.session.definition_document = document
    window.session.documents._documents[document.path] = document

    document_dock = window._show_editor(window._ensure_editor(document))
    window._show_generated_items("Groups")
    groups_dock = window._generated_docks["Groups"]

    assert document_dock.dockManager() is window.central_dock_manager
    assert groups_dock.dockManager() is window.central_dock_manager
    assert document_dock.dockAreaWidget() is groups_dock.dockAreaWidget()


def test_clear_problems_button_clears_displayed_diagnostics(qtbot, tmp_path) -> None:
    settings = QSettings(str(tmp_path / "clear-problems.ini"), QSettings.IniFormat)
    preferences = ApplicationPreferences(settings=settings)
    preferences.set_restore_last_session(False)
    window = MainWindow(application_preferences=preferences)
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
        pin_map=(),
        test_plans=(plan,),
        definition=SimpleNamespace(power_resources={}),
        stage=lambda _name: None,
    )

    window._rebuild_project_tree()

    root = window.project_tree.topLevelItem(0)
    generated = root.child(2)
    test_plans = generated.child(5)

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
    browse = window.project_tree.itemWidget(item, 1)
    assert browse is not None
    assert browse.objectName() == "inputFileBrowseButton_input_file"
    assert browse.text() == "Browse…"


def test_input_file_severity_icon_uses_decoration_role(qtbot, tmp_path) -> None:
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
    window._severity_for_location_token = lambda _token: "warning"

    window._rebuild_project_tree()

    item = window.project_tree.topLevelItem(0).child(0).child(0)
    icon = item.data(0, Qt.DecorationRole)
    assert icon is not None
    assert not icon.isNull()
    assert window.project_tree.itemWidget(item, 0) is None


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

    dock = window._show_editor(editor)
    window._update_tab_titles()
    root = window.project_tree.topLevelItem(0)
    assert dock.windowTitle() == "generation.yaml*"
    if hasattr(dock, "tabWidget") and dock.tabWidget() is not None:
        assert dock.tabWidget().font().italic()
    assert root.text(0) == "generation.yaml*"
    assert root.font(0).italic()


def test_default_tool_layout_uses_distinct_left_bottom_and_right_regions(qtbot) -> None:
    window = MainWindow()
    qtbot.addWidget(window)

    project_area = window.project_dock.dockAreaWidget()
    problems_area = window.problems_dock.dockAreaWidget()
    right_area = window.inspector_dock.dockAreaWidget()

    assert project_area is not problems_area
    assert project_area is not right_area
    assert problems_area is not right_area

    assert window.parsed_dock.dockAreaWidget() is right_area
    assert window.snapshot_dock.dockAreaWidget() is right_area
    assert window.document_workspace_dock.dockManager() is window.dock_manager


def test_center_workspace_is_empty_on_startup(qtbot) -> None:
    window = MainWindow()
    qtbot.addWidget(window)

    assert window._document_docks == {}
    assert window._generated_docks == {}
    assert window._central_dock_area() is None


def test_documents_and_generated_views_use_central_manager(qtbot, tmp_path) -> None:
    window = MainWindow()
    qtbot.addWidget(window)

    path = tmp_path / "generation.yaml"
    path.write_text("schema_version: 1.0\n", encoding="utf-8")
    document = TextDocument.load(path)
    window.session.definition_document = document
    window.session.documents._documents[document.path] = document

    document_dock = window._show_editor(window._ensure_editor(document))
    window._show_generated_items("Groups")
    groups_dock = window._generated_docks["Groups"]
    assert document_dock.dockManager() is window.central_dock_manager
    assert groups_dock.dockManager() is window.central_dock_manager
    assert document_dock.dockAreaWidget() is groups_dock.dockAreaWidget()


def test_layout_state_uses_new_key_after_default_topology_change(qtbot) -> None:
    window = MainWindow()
    qtbot.addWidget(window)

    assert window._docking_state_key == "docking/state"


def test_view_menu_starts_with_reset_layout_and_panels_submenu(qtbot) -> None:
    window = MainWindow()
    qtbot.addWidget(window)

    actions = window.view_menu.actions()
    assert actions[0] is window.reset_layout_action
    assert actions[0].text() == "Reset Layout"
    assert actions[1].isSeparator()
    assert actions[2].menu() is window.panels_menu
    assert actions[2].text() == "Panels"

    panel_actions = window.panels_menu.actions()
    expected = {
        window.project_dock.toggleViewAction().text(),
        window.inspector_dock.toggleViewAction().text(),
        window.problems_dock.toggleViewAction().text(),
        window.parsed_dock.toggleViewAction().text(),
        window.snapshot_dock.toggleViewAction().text(),
    }
    assert {action.text() for action in panel_actions} == expected


def test_reset_layout_restores_default_tool_regions(qtbot) -> None:
    window = MainWindow()
    qtbot.addWidget(window)

    window.dock_manager.addDockWidget(
        QtAds.DockWidgetArea.RightDockWidgetArea,
        window.project_dock,
    )
    window.project_dock.toggleView(False)

    window._reset_layout()

    project_area = window.project_dock.dockAreaWidget()
    right_area = window.inspector_dock.dockAreaWidget()
    problems_area = window.problems_dock.dockAreaWidget()

    assert not window.project_dock.isClosed()
    assert project_area is not right_area
    assert project_area is not problems_area


def test_export_status_progresses_to_clickable_exported_folder(qtbot, tmp_path, monkeypatch) -> None:
    settings = QSettings(str(tmp_path / "export-preferences.ini"), QSettings.IniFormat)
    preferences = ApplicationPreferences(settings=settings)
    preferences.set_open_folder_after_export(False)
    window = MainWindow(application_preferences=preferences)
    qtbot.addWidget(window)

    definition_path = tmp_path / "generation.yaml"
    definition_path.write_text("schema_version: 1.0\n", encoding="utf-8")
    window.session.definition_document = TextDocument.load(definition_path)
    export_root = tmp_path / "export"
    project_folder = export_root / "Example"
    project_path = project_folder / "Example.Prj"
    monkeypatch.setattr(window.session, "export_project_directory", lambda _output_directory: project_folder)

    monkeypatch.setattr(
        "project_generation_gui.main_window.QFileDialog.getExistingDirectory",
        lambda *_args, **_kwargs: str(export_root),
    )

    observed_statuses = []

    def export_project(_output_directory, *, overwrite=False):
        assert overwrite is False
        observed_statuses.append(window.export_status_label.text())
        project_folder.mkdir(parents=True)
        project_path.write_text("{}", encoding="utf-8")
        return project_path

    window.session.export_project = export_project

    window.export_project_dialog()

    assert observed_statuses == ["Exporting…"]
    assert window.export_status_label.text().startswith("Exported: <a href=")
    assert str(project_folder) in window.export_status_label.text()
    assert window.export_action.isEnabled()


def test_export_opens_folder_when_enabled(qtbot, tmp_path, monkeypatch) -> None:
    settings = QSettings(str(tmp_path / "export-open-preferences.ini"), QSettings.IniFormat)
    preferences = ApplicationPreferences(settings=settings)
    preferences.set_open_folder_after_export(True)
    window = MainWindow(application_preferences=preferences)
    qtbot.addWidget(window)

    definition_path = tmp_path / "generation.yaml"
    definition_path.write_text("schema_version: 1.0\n", encoding="utf-8")
    window.session.definition_document = TextDocument.load(definition_path)
    export_root = tmp_path / "export"
    project_folder = export_root / "Example"
    project_path = project_folder / "Example.Prj"
    monkeypatch.setattr(window.session, "export_project_directory", lambda _output_directory: project_folder)

    monkeypatch.setattr(
        "project_generation_gui.main_window.QFileDialog.getExistingDirectory",
        lambda *_args, **_kwargs: str(export_root),
    )
    window.session.export_project = lambda _output_directory, *, overwrite=False: project_path
    opened = []
    monkeypatch.setattr(window, "_open_folder", lambda path: opened.append(path))

    window.export_project_dialog()

    assert opened == [project_folder]


def test_export_failure_sets_failed_status(qtbot, tmp_path, monkeypatch) -> None:
    settings = QSettings(str(tmp_path / "export-failure-preferences.ini"), QSettings.IniFormat)
    preferences = ApplicationPreferences(settings=settings)
    window = MainWindow(application_preferences=preferences)
    qtbot.addWidget(window)

    definition_path = tmp_path / "generation.yaml"
    definition_path.write_text("schema_version: 1.0\n", encoding="utf-8")
    window.session.definition_document = TextDocument.load(definition_path)
    export_root = tmp_path / "export"
    project_folder = export_root / "Example"
    monkeypatch.setattr(
        "project_generation_gui.main_window.QFileDialog.getExistingDirectory",
        lambda *_args, **_kwargs: str(export_root),
    )
    monkeypatch.setattr(window.session, "export_project_directory", lambda _output_directory: project_folder)

    def fail_export(_output_directory, *, overwrite=False):
        raise RuntimeError("boom")

    window.session.export_project = fail_export

    window.export_project_dialog()

    assert window.export_status_label.text() == "Export failed"
    assert window.export_action.isEnabled()


def test_export_existing_project_prompts_before_overwrite(qtbot, tmp_path, monkeypatch) -> None:
    settings = QSettings(str(tmp_path / "export-overwrite-prompt.ini"), QSettings.IniFormat)
    preferences = ApplicationPreferences(settings=settings)
    preferences.set_open_folder_after_export(False)
    window = MainWindow(application_preferences=preferences)
    qtbot.addWidget(window)

    definition_path = tmp_path / "generation.yaml"
    definition_path.write_text("schema_version: 1.0\n", encoding="utf-8")
    window.session.definition_document = TextDocument.load(definition_path)
    export_root = tmp_path / "export"
    project_folder = export_root / "Example"
    project_folder.mkdir(parents=True)
    project_path = project_folder / "Example.Prj"

    monkeypatch.setattr(
        "project_generation_gui.main_window.QFileDialog.getExistingDirectory",
        lambda *_args, **_kwargs: str(export_root),
    )
    monkeypatch.setattr(window.session, "export_project_directory", lambda _output_directory: project_folder)
    monkeypatch.setattr(
        "project_generation_gui.main_window.QMessageBox.question",
        lambda *_args, **_kwargs: QMessageBox.Yes,
    )
    calls = []

    def export_project(_output_directory, *, overwrite=False):
        calls.append(overwrite)
        return project_path

    window.session.export_project = export_project
    window.export_project_dialog()

    assert calls == [True]


def test_overwrite_checkbox_skips_existing_project_prompt(qtbot, tmp_path, monkeypatch) -> None:
    settings = QSettings(str(tmp_path / "export-overwrite-checkbox.ini"), QSettings.IniFormat)
    preferences = ApplicationPreferences(settings=settings)
    preferences.set_open_folder_after_export(False)
    window = MainWindow(application_preferences=preferences)
    qtbot.addWidget(window)

    definition_path = tmp_path / "generation.yaml"
    definition_path.write_text("schema_version: 1.0\n", encoding="utf-8")
    window.session.definition_document = TextDocument.load(definition_path)
    export_root = tmp_path / "export"
    project_folder = export_root / "Example"
    project_folder.mkdir(parents=True)
    project_path = project_folder / "Example.Prj"

    monkeypatch.setattr(
        "project_generation_gui.main_window.QFileDialog.getExistingDirectory",
        lambda *_args, **_kwargs: str(export_root),
    )
    monkeypatch.setattr(window.session, "export_project_directory", lambda _output_directory: project_folder)
    monkeypatch.setattr(
        "project_generation_gui.main_window.QMessageBox.question",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("prompt should not be shown")),
    )
    calls = []

    def export_project(_output_directory, *, overwrite=False):
        calls.append(overwrite)
        return project_path

    window.session.export_project = export_project
    window.overwrite_existing_checkbox.setChecked(True)
    window.export_project_dialog()

    assert calls == [True]


def test_existing_project_cancel_does_not_export(qtbot, tmp_path, monkeypatch) -> None:
    settings = QSettings(str(tmp_path / "export-overwrite-cancel.ini"), QSettings.IniFormat)
    preferences = ApplicationPreferences(settings=settings)
    window = MainWindow(application_preferences=preferences)
    qtbot.addWidget(window)

    definition_path = tmp_path / "generation.yaml"
    definition_path.write_text("schema_version: 1.0\n", encoding="utf-8")
    window.session.definition_document = TextDocument.load(definition_path)
    export_root = tmp_path / "export"
    project_folder = export_root / "Example"
    project_folder.mkdir(parents=True)

    monkeypatch.setattr(
        "project_generation_gui.main_window.QFileDialog.getExistingDirectory",
        lambda *_args, **_kwargs: str(export_root),
    )
    monkeypatch.setattr(window.session, "export_project_directory", lambda _output_directory: project_folder)
    monkeypatch.setattr(
        "project_generation_gui.main_window.QMessageBox.question",
        lambda *_args, **_kwargs: QMessageBox.No,
    )
    monkeypatch.setattr(
        window.session,
        "export_project",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("export should not run")),
    )

    window.export_project_dialog()

    assert window.export_status_label.text() == "Export cancelled"
