from qtpy.QtWidgets import QLabel

from project_generation_gui.widgets import EditorArea


def test_editor_area_uses_closable_tabs(qtbot) -> None:
    area = EditorArea()
    qtbot.addWidget(area)
    first = QLabel("first")
    second = QLabel("second")
    area.add_editor(first, "first")
    area.add_editor(second, "second")

    tabs = next(area.iter_editors())[0]
    assert tabs.tabsClosable()
    assert {editor for _group, _index, editor in area.iter_editors()} == {first, second}


def test_closing_tab_removes_only_the_view_and_allows_reopen(qtbot) -> None:
    area = EditorArea()
    qtbot.addWidget(area)
    editor = QLabel("editor")
    area.add_editor(editor, "editor")

    closed = []
    area.editor_closed.connect(closed.append)
    tabs = next(area.iter_editors())[0]
    tabs.tabCloseRequested.emit(0)

    assert closed == [editor]
    assert not area.contains_editor(editor)

    area.add_editor(editor, "editor")
    assert area.contains_editor(editor)
    assert area.current_editor() is editor
