import pytest

pytest.importorskip("pyqtgraph")

from project_generation.definition.models import PowerResourceDefinition
from project_generation_gui.colors import ColorTheme
from project_generation_gui.power_envelope import (
    EnvelopeMode,
    PowerEnvelopeComparisonView,
    regions_from_power_resources,
    requested_configuration_from_stress,
    requested_configurations_from_stress,
)


def test_regions_keep_hardware_assignment() -> None:
    resources = {
        "DC1": PowerResourceDefinition(
            role="STRESS",
            parameters={
                "power_envelopes": {
                    "DC": [{"max_voltage": 30.0, "max_current": 1.0}],
                    "PULSE": [{"max_peak_voltage": 100.0, "max_peak_current": 0.2}],
                }
            },
        ),
        "DC2": PowerResourceDefinition(
            role="STRESS",
            parameters={
                "power_envelopes": {
                    "PULSE": [{"max_peak_voltage": 300.0, "max_peak_current": 1.0}],
                }
            },
        ),
    }

    regions = regions_from_power_resources(resources)

    assert [(region.assignment, region.mode) for region in regions] == [
        ("DC1", EnvelopeMode.DC),
        ("DC1", EnvelopeMode.PULSE),
        ("DC2", EnvelopeMode.PULSE),
    ]


def test_requested_current_source_uses_compliance_as_voltage() -> None:
    requested = requested_configuration_from_stress(
        {"source_mode": "current", "peak": -0.15, "compliance": -7.5},
        assignment="DC5",
        supported=True,
    )

    assert requested is not None
    assert requested.voltage_v == -7.5
    assert requested.current_a == -0.15
    assert requested.assignment == "DC5"


def test_comparison_view_shows_only_selected_bus(qtbot) -> None:
    resources = {
        "DC1": PowerResourceDefinition(
            role="STRESS",
            parameters={"power_envelopes": {"DC": [{"max_voltage": 30.0, "max_current": 1.0}]}},
        ),
        "DC2": PowerResourceDefinition(
            role="STRESS",
            parameters={"power_envelopes": {"PULSE": [{"max_peak_voltage": 300.0, "max_peak_current": 1.0}]}},
        ),
    }
    view = PowerEnvelopeComparisonView(ColorTheme())
    qtbot.addWidget(view)
    view.set_power_resources(resources)

    assert view.current_assignment() == "DC1"
    assert {region.assignment for region in view.visible_regions()} == {"DC1"}

    requested = requested_configuration_from_stress(
        {"source_mode": "voltage", "peak": 100.0, "compliance": 0.2},
        assignment="DC2",
        supported=True,
    )
    view.set_requested_configuration(requested)

    assert view.current_assignment() == "DC2"
    assert {region.assignment for region in view.visible_regions()} == {"DC2"}


def test_comparison_view_shows_all_requested_configurations(qtbot) -> None:
    resources = {
        "DC1": PowerResourceDefinition(
            role="STRESS",
            parameters={"power_envelopes": {"DC": [{"max_voltage": 30.0, "max_current": 1.0}]}},
        ),
    }
    view = PowerEnvelopeComparisonView(ColorTheme())
    qtbot.addWidget(view)
    view.set_power_resources(resources)
    requests = [
        requested_configuration_from_stress(
            {"source_mode": "voltage", "peak": 5.0, "compliance": 0.1},
            assignment="DC1",
            supported=True,
            label="Point 1",
        ),
        requested_configuration_from_stress(
            {"source_mode": "voltage", "peak": 10.0, "compliance": 0.2},
            assignment="DC1",
            supported=True,
            label="Point 2",
        ),
    ]
    view.set_requested_configurations([request for request in requests if request is not None], selected_index=1)

    assert len(view._requested) == 2
    assert view._selected_requested_index == 1


def test_requested_bias_uses_generated_device_state_keys() -> None:
    from project_generation_gui.power_envelope import requested_configuration_from_bias

    requested = requested_configuration_from_bias(
        {"mode": "VOLTAGE", "level": 5.5, "compliance_limit": 0.25},
        assignment="DC2",
        label="Bias: 5V5",
    )

    assert requested is not None
    assert requested.voltage_v == 5.5
    assert requested.current_a == 0.25
    assert requested.assignment == "DC2"
    assert requested.label == "Bias: 5V5"


def test_requested_current_bias_uses_generated_device_state_keys() -> None:
    from project_generation_gui.power_envelope import requested_configuration_from_bias

    requested = requested_configuration_from_bias(
        {"mode": "CURRENT", "level": -0.15, "compliance_limit": -7.5},
        assignment="DC4",
        label="Bias: current",
    )

    assert requested is not None
    assert requested.voltage_v == -7.5
    assert requested.current_a == -0.15
    assert requested.assignment == "DC4"


def test_grid_uses_separate_plot_per_bus(qtbot) -> None:
    from project_generation_gui.power_envelope import PowerEnvelopeGridView, RequestedConfiguration

    resources = {
        "DC1": PowerResourceDefinition(
            role="STRESS",
            parameters={"power_envelopes": {"DC": [{"max_voltage": 30.0, "max_current": 1.0}]}},
        ),
        "DC2": PowerResourceDefinition(
            role="STRESS",
            parameters={"power_envelopes": {"DC": [{"max_voltage": 100.0, "max_current": 0.2}]}},
        ),
    }
    grid = PowerEnvelopeGridView(ColorTheme())
    qtbot.addWidget(grid)
    grid.set_power_resources(resources)
    grid.set_configurations(
        {
            "DC1": [RequestedConfiguration(voltage_v=5.0, current_a=0.1, assignment="DC1")],
            "DC2": [RequestedConfiguration(voltage_v=50.0, current_a=0.1, assignment="DC2")],
        }
    )

    assert grid.assignments() == ("DC1", "DC2")
    assert {region.assignment for region in grid.plots_by_assignment["DC1"].visible_regions()} == {"DC1"}
    assert {region.assignment for region in grid.plots_by_assignment["DC2"].visible_regions()} == {"DC2"}


def test_axis_map_can_use_linear_coordinates() -> None:
    from project_generation_gui.power_envelope import AxisMap

    axis = AxisMap([30.0, 300.0], range_scaled=False)

    assert axis.to_plot(-30.0) == -30.0
    assert axis.to_plot(150.0) == 150.0
    assert axis.extent == 300.0


def test_comparison_view_defaults_to_linear_axes(qtbot) -> None:
    view = PowerEnvelopeComparisonView(ColorTheme())
    qtbot.addWidget(view)

    assert view.range_scaled_axes() is False

    view.set_range_scaled_axes(True)

    assert view.range_scaled_axes() is True


def test_dc_and_pulse_envelopes_use_distinct_outlines_and_colors(qtbot) -> None:
    from qtpy import QtCore, QtWidgets

    resources = {
        "DC1": PowerResourceDefinition(
            role="STRESS",
            parameters={
                "power_envelopes": {
                    "DC": [{"max_voltage": 30.0, "max_current": 1.0}],
                    "PULSE": [{"max_peak_voltage": 100.0, "max_peak_current": 0.2}],
                }
            },
        ),
    }
    view = PowerEnvelopeComparisonView(ColorTheme())
    qtbot.addWidget(view)
    view.set_power_resources(resources)

    rectangles = [
        item
        for item in view.plot.plotItem.items
        if isinstance(item, QtWidgets.QGraphicsRectItem)
    ]
    assert len(rectangles) == 2

    try:
        solid = QtCore.Qt.PenStyle.SolidLine
        dashed = QtCore.Qt.PenStyle.DashLine
    except AttributeError:
        solid = QtCore.Qt.SolidLine
        dashed = QtCore.Qt.DashLine

    assert {item.pen().style() for item in rectangles} == {solid, dashed}
    assert len({item.brush().color().name() for item in rectangles}) == 2
    assert sorted(item.pen().width() for item in rectangles) == [2, 3]


def test_stress_request_produces_base_and_peak_pair() -> None:
    pair = requested_configurations_from_stress(
        {
            "source_mode": "current",
            "base_level": 0.0,
            "base_limit": -5.0,
            "peak_level": -0.12,
            "peak_limit": -7.5,
        },
        assignment="DC1",
        supported=True,
        label="Point 1",
        pair_id="p1",
    )

    assert len(pair) == 2
    base, peak = pair
    assert (base.voltage_v, base.current_a, base.marker, base.pair_id) == (-5.0, 0.0, "bias", "p1")
    assert (peak.voltage_v, peak.current_a, peak.marker, peak.pair_id) == (-7.5, -0.12, "pulse", "p1")


def test_comparison_view_has_no_footer_status_label(qtbot) -> None:
    view = PowerEnvelopeComparisonView(ColorTheme())
    qtbot.addWidget(view)

    assert not hasattr(view, "status")
