from qtpy.QtCore import QSettings
from qtpy.QtGui import QColor

from project_generation_gui.colors import ASSIGNMENT_CATEGORY, TYPE_CATEGORY, ColorTheme


def make_theme(tmp_path) -> ColorTheme:
    settings = QSettings(str(tmp_path / "colors.ini"), QSettings.IniFormat)
    settings.clear()
    return ColorTheme(settings=settings)


def test_unknown_values_receive_stable_colors(tmp_path) -> None:
    theme = make_theme(tmp_path)

    first = theme.color(TYPE_CATEGORY, "CUSTOM_TYPE")
    second = theme.color(TYPE_CATEGORY, "CUSTOM_TYPE")

    assert first.isValid()
    assert first == second


def test_color_override_is_persisted(tmp_path) -> None:
    settings = QSettings(str(tmp_path / "colors.ini"), QSettings.IniFormat)
    settings.clear()
    theme = ColorTheme(settings=settings)
    theme.set_override(ASSIGNMENT_CATEGORY, "DC9", QColor("#123456"))

    restored = ColorTheme(settings=settings)

    assert restored.color(ASSIGNMENT_CATEGORY, "DC9").name() == "#123456"


def test_register_values_exposes_new_settings_options(tmp_path) -> None:
    theme = make_theme(tmp_path)

    theme.register_values(TYPE_CATEGORY, ["ANALOG", "SPECIAL"])

    assert "ANALOG" in theme.values(TYPE_CATEGORY)
    assert "SPECIAL" in theme.values(TYPE_CATEGORY)


def test_custom_values_are_persisted_renamed_and_removed(tmp_path) -> None:
    settings = QSettings(str(tmp_path / "colors.ini"), QSettings.IniFormat)
    settings.clear()
    theme = ColorTheme(settings=settings)

    theme.add_custom_value(TYPE_CATEGORY, "ANALOG")
    original = theme.color(TYPE_CATEGORY, "ANALOG")
    theme.rename_custom_value(TYPE_CATEGORY, "ANALOG", "ANALOG_INPUT")

    restored = ColorTheme(settings=settings)
    assert "ANALOG" not in restored.values(TYPE_CATEGORY)
    assert "ANALOG_INPUT" in restored.values(TYPE_CATEGORY)
    assert restored.color(TYPE_CATEGORY, "ANALOG_INPUT") == original

    restored.remove_custom_value(TYPE_CATEGORY, "ANALOG_INPUT")
    final = ColorTheme(settings=settings)
    assert "ANALOG_INPUT" not in final.values(TYPE_CATEGORY)


def test_next_color_cycle_is_independent_per_category(tmp_path) -> None:
    theme = make_theme(tmp_path)

    type_color = theme.next_color(TYPE_CATEGORY)
    assignment_color = theme.next_color(ASSIGNMENT_CATEGORY)
    theme.add_custom_value(TYPE_CATEGORY, "ANALOG", type_color)

    assert theme.next_color(ASSIGNMENT_CATEGORY) == assignment_color
    assert theme.next_color(TYPE_CATEGORY) != type_color


def test_discovered_assignment_values_continue_palette_cycle(tmp_path) -> None:
    theme = make_theme(tmp_path)

    theme.register_values(ASSIGNMENT_CATEGORY, ["GROUND", "FLOATING", "DC1", "DC2", "DC3", "DC4", "DC5", "DC6"])

    assert theme.color(ASSIGNMENT_CATEGORY, "DC5").name().upper() == "#EC407A"
    assert theme.color(ASSIGNMENT_CATEGORY, "DC6").name().upper() == "#7E57C2"
    theme.register_values(ASSIGNMENT_CATEGORY, ["DC7"])
    assert theme.color(ASSIGNMENT_CATEGORY, "DC7").name().upper() == "#42A5F5"


def test_discovered_color_cycles_are_independent_by_category(tmp_path) -> None:
    theme = make_theme(tmp_path)

    theme.register_values(ASSIGNMENT_CATEGORY, ["DC5"])
    assignment_color = theme.color(ASSIGNMENT_CATEGORY, "DC5")
    theme.register_values(TYPE_CATEGORY, ["ANALOG"])

    assert assignment_color.name().upper() == "#EC407A"
    assert theme.color(ASSIGNMENT_CATEGORY, "DC5") == assignment_color
