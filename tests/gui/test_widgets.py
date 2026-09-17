from pathlib import Path
from uuid import uuid4

from qtpy.QtCore import QSettings, Qt
from qtpy.QtGui import QColor, QTextCursor
from qtpy.QtWidgets import QPlainTextEdit

from project_generation.generation.models import (
    GeneratedDeviceState,
    GeneratedGroup,
    GeneratedPin,
    GeneratedPowerDomain,
    GeneratedTestGroup,
    GeneratedTestPlan,
)
from project_generation.generation.rules import StressPoint
from project_generation_gui.colors import ColorTheme
from project_generation_gui.syntax_highlighting import style_name_for_background
from project_generation_gui.widgets import TestPlansView, TextEditor


def make_theme(tmp_path) -> ColorTheme:
    settings = QSettings(str(tmp_path / "colors.ini"), QSettings.IniFormat)
    settings.clear()
    return ColorTheme(settings=settings)


def test_syntax_style_follows_editor_background() -> None:
    assert style_name_for_background(QColor("#202124")) == "one-dark"
    assert style_name_for_background(QColor("#ffffff")) == "default"


def test_text_editor_uses_pygments_lexer_for_document_type(qtbot) -> None:
    yaml_editor = TextEditor(Path("generation.yaml"), "schema_version: '1.0'\n")
    json_editor = TextEditor(Path("input.json"), '{"value": 1}')
    qtbot.addWidget(yaml_editor)
    qtbot.addWidget(json_editor)

    assert "yaml" in yaml_editor._search_highlighter.lexer.name.lower()
    assert "json" in json_editor._search_highlighter.lexer.name.lower()


def test_yaml_pygments_tokens_fall_back_to_parent_style(qtbot) -> None:
    editor = TextEditor(Path("generation.yaml"), "source: value\nitems:\n  - first\n")
    qtbot.addWidget(editor)

    token_types = {
        token_type
        for _start, token_type, value in editor._search_highlighter.lexer.get_tokens_unprocessed(
            editor.toPlainText()
        )
        if value
    }

    # YAML emits lexer-specific descendants that are not necessarily explicit
    # entries in a Pygments style. Every emitted token must still resolve via
    # its nearest styled parent without raising KeyError.
    for token_type in token_types:
        editor._search_highlighter._format_for_token(token_type)


def test_text_editor_find_highlights_all_matches_and_moves_cursor_to_navigation_match(qtbot) -> None:
    editor = TextEditor(Path("example.yaml"), "alpha beta alpha gamma alpha")
    qtbot.addWidget(editor)
    editor.show()

    editor.show_search()
    editor.search_edit.setText("alpha")

    assert editor.search_count.text() == "1/3"
    assert editor._search_highlighter._matches == ((0, 5), (11, 16), (23, 28))
    assert editor._search_highlighter._current_match == (0, 5)

    qtbot.keyClick(editor.search_edit, Qt.Key_Return)
    assert editor.search_count.text() == "2/3"
    assert editor._search_highlighter._current_match == (11, 16)
    assert editor.textCursor().selectionStart() == 11
    assert editor.textCursor().selectionEnd() == 16

    qtbot.keyClick(editor.search_edit, Qt.Key_Return)
    assert editor.search_count.text() == "3/3"
    assert editor.textCursor().selectionStart() == 23
    assert editor.textCursor().selectionEnd() == 28

    qtbot.keyClick(editor.search_edit, Qt.Key_Return)
    assert editor.search_count.text() == "1/3"
    assert editor.textCursor().selectionStart() == 0
    assert editor.textCursor().selectionEnd() == 5

    qtbot.keyClick(editor.search_edit, Qt.Key_Return, modifier=Qt.ShiftModifier)
    assert editor.search_count.text() == "3/3"
    assert editor.textCursor().selectionStart() == 23
    assert editor.textCursor().selectionEnd() == 28

    # User movement/editing invalidates the navigation position. The next search
    # anchors from the real editor cursor and then selects that match.
    cursor = editor.textCursor()
    cursor.clearSelection()
    cursor.setPosition(6)
    editor.setTextCursor(cursor)
    editor.setFocus()
    qtbot.keyClicks(editor, "x")
    assert editor.search_count.text() == "0/3"
    assert editor._search_highlighter._current_match is None

    editor.search_edit.setFocus()
    qtbot.keyClick(editor.search_edit, Qt.Key_Return)
    assert editor.search_count.text() == "2/3"
    assert editor._search_highlighter._current_match == (12, 17)
    assert editor.textCursor().selectionStart() == 12
    assert editor.textCursor().selectionEnd() == 17

    # A query with no results clears every search highlight and current match.
    editor.search_edit.setText("not-present")
    assert editor.search_count.text() == "0/0"
    assert editor._search_highlighter._matches == ()
    assert editor._search_highlighter._current_match is None


def test_text_editor_find_keeps_shortcuts_and_uses_document_match_spans(qtbot) -> None:
    editor = TextEditor(Path("example.yaml"), "Alpha alpha ALPHA")
    qtbot.addWidget(editor)
    editor.show()

    assert len(editor._search_shortcuts) == 3

    editor.show_search()
    editor.search_edit.setText("alpha")

    # QTextDocument.find() defines the matching semantics; the highlighter is
    # given those exact spans instead of independently re-finding text.
    assert tuple(editor._search_matches) == editor._search_highlighter._matches
    assert len(editor._search_highlighter._matches) == len(editor._search_matches)


def test_test_plan_stress_view_shows_resolved_device_state_power_domains(qtbot, tmp_path) -> None:
    pin = GeneratedPin(id=uuid4(), designator="1", name="VDD", parameters={"pin_type": "POWER"})
    group = GeneratedGroup(
        id=uuid4(),
        name="Su5V0",
        group_type="POWER",
        pin_ids=(pin.id,),
        bias_spec={"mode": "VOLTAGE", "level": 5.0},
    )
    state = GeneratedDeviceState(
        id=uuid4(),
        name="powered",
        extends=None,
        power_domains=(
            GeneratedPowerDomain(
                name="5V0",
                group_ids=(group.id,),
                group_names=(group.name,),
                assignment="DC1",
                bias={"mode": "VOLTAGE", "level": 5.0, "compliance_limit": 0.2},
            ),
        ),
        power_on_sequence=(),
        power_off_sequence=(),
    )
    plan = GeneratedTestPlan(
        id=uuid4(),
        name="LU_Su5V0",
        test_type="SUPPLY",
        dimensions={},
        device_state=state.name,
        device_state_id=state.id,
        test_groups=(
            GeneratedTestGroup(
                group_id=group.id,
                group_name=group.name,
                stress_points=(StressPoint(values={"level": 7.5}),),
            ),
        ),
    )

    view = TestPlansView(make_theme(tmp_path))
    qtbot.addWidget(view)
    view.set_plans([plan], [group], [pin], [state], {})

    assert view.details.currentIndex() == 0
    assert view.stress_device_state_label.text() == "Device State — powered"
    assert view.stress_device_state._source_model.rowCount() == 1
    assert view.stress_device_state._source_model.item(0, 0).text() == "5V0"
    assert view.stress_device_state._source_model.item(0, 1).text() == "DC1"
    assert not view.stress_points.currentIndex().isValid()
    assert not view.stress_points.selectionModel().hasSelection()


def test_test_plan_clear_details_clears_power_envelope_grid(qtbot, tmp_path) -> None:
    view = TestPlansView(make_theme(tmp_path))
    qtbot.addWidget(view)

    view._clear_details()

    assert view.power_envelope.assignments() == ()


def test_text_editor_disables_word_wrap(qtbot) -> None:
    editor = TextEditor(Path("generation.yaml"), "key: value\n")
    qtbot.addWidget(editor)
    assert editor.lineWrapMode() == QPlainTextEdit.NoWrap


def test_text_editor_font_size_can_be_changed(qtbot) -> None:
    editor = TextEditor(Path("generation.yaml"), "key: value\n")
    qtbot.addWidget(editor)
    editor.set_font_size(14)
    assert editor.font().pointSize() == 14
