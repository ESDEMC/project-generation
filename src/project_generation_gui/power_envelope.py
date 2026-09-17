from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Mapping, Sequence

import pyqtgraph as pg
from qtpy import QtCore, QtGui, QtWidgets

from project_generation.definition.models import PowerResourceDefinition
from project_generation_gui.colors import ASSIGNMENT_CATEGORY, ColorTheme
from project_generation_gui.display_formatting import format_quantity


class EnvelopeMode(StrEnum):
    DC = "DC"
    PULSE = "PULSE"


def _solid_line_style():
    try:
        return QtCore.Qt.PenStyle.SolidLine
    except AttributeError:
        return QtCore.Qt.SolidLine


def _dash_line_style():
    try:
        return QtCore.Qt.PenStyle.DashLine
    except AttributeError:
        return QtCore.Qt.DashLine


@dataclass(frozen=True, kw_only=True)
class PowerEnvelopeRegion:
    assignment: str
    mode: EnvelopeMode
    max_abs_voltage_v: float
    max_abs_current_a: float
    details: Mapping[str, Any]

    @property
    def name(self) -> str:
        return (
            f"{self.assignment} {self.mode}: "
            f"{format_quantity(self.max_abs_voltage_v, 'V')} @ "
            f"{format_quantity(self.max_abs_current_a, 'A')}"
        )


@dataclass(frozen=True, kw_only=True)
class RequestedConfiguration:
    voltage_v: float
    current_a: float
    assignment: str | None = None
    supported: bool = True
    tooltip: str | None = None
    label: str | None = None
    marker: str = "bias"
    pair_id: str | None = None


class AxisMap:
    """Map physical values either linearly or onto range-scaled breakpoints."""

    def __init__(self, values: Sequence[float], *, range_scaled: bool) -> None:
        breakpoints = sorted({0.0, *(abs(float(value)) for value in values if value is not None)})
        self.breakpoints = breakpoints if len(breakpoints) > 1 else [0.0, 1.0]
        self.range_scaled = range_scaled

    def to_plot(self, value: float) -> float:
        if not self.range_scaled:
            return float(value)
        if value == 0:
            return 0.0
        sign = -1.0 if value < 0 else 1.0
        value = abs(value)
        if value >= self.breakpoints[-1]:
            return sign * float(len(self.breakpoints) - 1)
        for index in range(1, len(self.breakpoints)):
            low = self.breakpoints[index - 1]
            high = self.breakpoints[index]
            if low <= value <= high:
                if high == low:
                    return sign * float(index - 1)
                return sign * ((index - 1) + ((value - low) / (high - low)))
        return 0.0

    @property
    def extent(self) -> float:
        if self.range_scaled:
            return float(len(self.breakpoints) - 1)
        return self.breakpoints[-1]

    def ticks(self, unit: str) -> list[tuple[float, str]]:
        positive = [(self.to_plot(value), self._format(value, unit)) for value in self.breakpoints]
        negative = [
            (self.to_plot(-value), self._format(-value, unit))
            for value in reversed(self.breakpoints[1:])
        ]
        return negative + positive

    @staticmethod
    def _format(value: float, unit: str) -> str:
        if value == 0:
            return "0"
        return format_quantity(value, unit)


def regions_from_power_resources(
    power_resources: Mapping[str, PowerResourceDefinition],
) -> tuple[PowerEnvelopeRegion, ...]:
    regions: list[PowerEnvelopeRegion] = []
    for assignment, resource in power_resources.items():
        envelopes = resource.parameters.get("power_envelopes") or {}
        if not isinstance(envelopes, Mapping):
            continue
        for raw in envelopes.get("DC") or ():
            if not isinstance(raw, Mapping):
                continue
            voltage = raw.get("max_voltage")
            current = raw.get("max_current")
            if voltage is None or current is None:
                continue
            regions.append(
                PowerEnvelopeRegion(
                    assignment=assignment,
                    mode=EnvelopeMode.DC,
                    max_abs_voltage_v=abs(float(voltage)),
                    max_abs_current_a=abs(float(current)),
                    details=dict(raw),
                )
            )
        for raw in envelopes.get("PULSE") or ():
            if not isinstance(raw, Mapping):
                continue
            voltage = raw.get("max_peak_voltage")
            current = raw.get("max_peak_current")
            if voltage is None or current is None:
                continue
            regions.append(
                PowerEnvelopeRegion(
                    assignment=assignment,
                    mode=EnvelopeMode.PULSE,
                    max_abs_voltage_v=abs(float(voltage)),
                    max_abs_current_a=abs(float(current)),
                    details=dict(raw),
                )
            )
    return tuple(regions)


def _operating_xy(mode: str, level: float, limit: float) -> tuple[float, float]:
    if mode == "current":
        return float(limit), float(level)
    return float(level), float(limit)


def requested_configurations_from_stress(
    values: Mapping[str, Any],
    *,
    assignment: str | None,
    supported: bool,
    tooltip: str | None = None,
    label: str | None = None,
    pair_id: str | None = None,
) -> tuple[RequestedConfiguration, RequestedConfiguration] | tuple[()]:
    mode = str(values.get("source_mode") or "voltage").lower()
    legacy_limit = values.get("compliance", values.get("compliance_limit", 0.0))
    base_level = values.get("base_level", values.get("base", values.get("bias_level", 0.0)))
    peak_level = values.get("peak_level", values.get("peak"))
    if peak_level is None:
        return ()
    base_limit = values.get(
        "base_limit",
        values.get("bias_compliance", values.get("bias_compliance_limit", legacy_limit)),
    )
    peak_limit = values.get("peak_limit", legacy_limit)
    base_limit = 0.0 if base_limit is None else float(base_limit)
    peak_limit = 0.0 if peak_limit is None else float(peak_limit)
    pair_id = pair_id or label
    base_voltage, base_current = _operating_xy(mode, float(base_level), base_limit)
    peak_voltage, peak_current = _operating_xy(mode, float(peak_level), peak_limit)
    base_label = f"{label} base" if label else "Base"
    peak_label = f"{label} peak" if label else "Peak"
    return (
        RequestedConfiguration(
            voltage_v=base_voltage,
            current_a=base_current,
            assignment=assignment,
            supported=supported,
            tooltip=tooltip,
            label=base_label,
            marker="bias",
            pair_id=pair_id,
        ),
        RequestedConfiguration(
            voltage_v=peak_voltage,
            current_a=peak_current,
            assignment=assignment,
            supported=supported,
            tooltip=tooltip,
            label=peak_label,
            marker="pulse",
            pair_id=pair_id,
        ),
    )


def requested_configuration_from_stress(
    values: Mapping[str, Any],
    *,
    assignment: str | None,
    supported: bool,
    tooltip: str | None = None,
    label: str | None = None,
) -> RequestedConfiguration | None:
    """Compatibility helper returning the peak configuration."""
    pair = requested_configurations_from_stress(
        values,
        assignment=assignment,
        supported=supported,
        tooltip=tooltip,
        label=label,
    )
    return pair[1] if pair else None


class PowerEnvelopeComparisonView(QtWidgets.QWidget):
    """Show one hardware bus envelope with zero or more requested configurations."""

    def __init__(self, theme: ColorTheme, parent=None) -> None:
        super().__init__(parent)
        self._theme = theme
        self._regions: tuple[PowerEnvelopeRegion, ...] = ()
        self._requested: tuple[RequestedConfiguration, ...] = ()
        self._selected_requested_index: int | None = None

        self.bus_combo = QtWidgets.QComboBox()
        self.bus_combo.currentIndexChanged.connect(self._rebuild)

        self.axis_mode_combo = QtWidgets.QComboBox()
        self.axis_mode_combo.addItem("Linear", False)
        self.axis_mode_combo.addItem("Range-scaled", True)
        self.axis_mode_combo.currentIndexChanged.connect(self._rebuild)

        self.plot = pg.PlotWidget()
        self.plot.hideButtons()
        self.legend = self.plot.addLegend()
        self.plot.setLabel("bottom", "Voltage", units="V")
        self.plot.setLabel("left", "Current", units="A")
        self.plot.showGrid(x=True, y=True, alpha=0.2)

        self.selector_widget = QtWidgets.QWidget()
        selector_layout = QtWidgets.QHBoxLayout(self.selector_widget)
        selector_layout.setContentsMargins(0, 0, 0, 0)
        self.bus_label = QtWidgets.QLabel("Bus")
        selector_layout.addWidget(self.bus_label)
        selector_layout.addWidget(self.bus_combo)
        selector_layout.addSpacing(12)
        selector_layout.addWidget(QtWidgets.QLabel("Axes"))
        selector_layout.addWidget(self.axis_mode_combo)
        selector_layout.addStretch(1)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.selector_widget)
        layout.addWidget(self.plot, 1)

        self._theme.changed.connect(self._rebuild)

    def set_power_resources(self, resources: Mapping[str, PowerResourceDefinition]) -> None:
        self._regions = regions_from_power_resources(resources)
        assignments = list(dict.fromkeys(region.assignment for region in self._regions))
        self._theme.register_values(ASSIGNMENT_CATEGORY, assignments)

        previous = self.current_assignment()
        self.bus_combo.blockSignals(True)
        self.bus_combo.clear()
        for assignment in assignments:
            self.bus_combo.addItem(assignment, assignment)
        if previous in assignments:
            self.bus_combo.setCurrentIndex(assignments.index(previous))
        self.bus_combo.blockSignals(False)
        self._select_requested_assignment()
        self._rebuild()

    def set_assignment(self, assignment: str) -> None:
        index = self.bus_combo.findData(assignment)
        if index >= 0:
            self.bus_combo.setCurrentIndex(index)

    def set_bus_selector_visible(self, visible: bool) -> None:
        self.bus_label.setVisible(visible)
        self.bus_combo.setVisible(visible)

    def set_range_scaled_axes(self, enabled: bool) -> None:
        index = self.axis_mode_combo.findData(bool(enabled))
        if index >= 0:
            self.axis_mode_combo.setCurrentIndex(index)

    def range_scaled_axes(self) -> bool:
        return bool(self.axis_mode_combo.currentData())

    def set_requested_configuration(self, requested: RequestedConfiguration | None) -> None:
        self.set_requested_configurations(() if requested is None else (requested,))

    def set_requested_configurations(
        self,
        requested: Sequence[RequestedConfiguration],
        *,
        selected_index: int | None = None,
    ) -> None:
        self._requested = tuple(requested)
        self._selected_requested_index = selected_index
        self._select_requested_assignment()
        self._rebuild()

    def current_assignment(self) -> str | None:
        assignment = self.bus_combo.currentData()
        return str(assignment) if assignment is not None else None

    def visible_regions(self) -> tuple[PowerEnvelopeRegion, ...]:
        assignment = self.current_assignment()
        if assignment is None:
            return ()
        return tuple(region for region in self._regions if region.assignment == assignment)

    def _select_requested_assignment(self) -> None:
        requested = next((item for item in self._requested if item.assignment is not None), None)
        if requested is None:
            return
        index = self.bus_combo.findData(requested.assignment)
        if index >= 0 and index != self.bus_combo.currentIndex():
            self.bus_combo.blockSignals(True)
            self.bus_combo.setCurrentIndex(index)
            self.bus_combo.blockSignals(False)

    def _rebuild(self) -> None:
        self.plot.clear()
        self.legend.clear()
        background = self.palette().base().color()
        foreground = self.palette().text().color()
        self.plot.setBackground(background)
        for axis_name in ("bottom", "left"):
            axis = self.plot.getAxis(axis_name)
            axis.setPen(foreground)
            axis.setTextPen(foreground)

        requested = self._requested
        visible_regions = self.visible_regions()
        voltage_values = [region.max_abs_voltage_v for region in visible_regions]
        current_values = [region.max_abs_current_a for region in visible_regions]
        voltage_values.extend(abs(item.voltage_v) for item in requested)
        current_values.extend(abs(item.current_a) for item in requested)
        range_scaled = self.range_scaled_axes()
        x_map = AxisMap(voltage_values, range_scaled=range_scaled)
        y_map = AxisMap(current_values, range_scaled=range_scaled)

        if range_scaled:
            self.plot.getAxis("bottom").setTicks([x_map.ticks("V")])
            self.plot.getAxis("left").setTicks([y_map.ticks("A")])
        else:
            self.plot.getAxis("bottom").setTicks(None)
            self.plot.getAxis("left").setTicks(None)
        self.plot.addItem(pg.InfiniteLine(pos=0, angle=90, pen=pg.mkPen("#777777", width=1)))
        self.plot.addItem(pg.InfiniteLine(pos=0, angle=0, pen=pg.mkPen("#777777", width=1)))

        ordered = sorted(
            visible_regions,
            key=lambda region: region.max_abs_voltage_v * region.max_abs_current_a,
            reverse=True,
        )
        for index, region in enumerate(ordered):
            bus_color = QtGui.QColor(self._theme.color(ASSIGNMENT_CATEGORY, region.assignment))
            if region.mode == EnvelopeMode.DC:
                region_color = bus_color.lighter(175)
                outline_color = QtGui.QColor(bus_color)
                fill_alpha = 70
                pen_width = 2
                pen_style = _solid_line_style()
            else:
                region_color = bus_color.darker(150)
                outline_color = region_color.darker(115)
                fill_alpha = 115
                pen_width = 3
                pen_style = _dash_line_style()

            fill = QtGui.QColor(region_color)
            fill.setAlpha(fill_alpha)
            pen_color = QtGui.QColor(outline_color)
            pen_color.setAlpha(245)
            pen = QtGui.QPen(pen_color)
            pen.setCosmetic(True)
            pen.setWidth(pen_width)
            pen.setStyle(pen_style)

            x0 = x_map.to_plot(-region.max_abs_voltage_v)
            x1 = x_map.to_plot(region.max_abs_voltage_v)
            y0 = y_map.to_plot(-region.max_abs_current_a)
            y1 = y_map.to_plot(region.max_abs_current_a)
            rect = QtWidgets.QGraphicsRectItem(QtCore.QRectF(x0, y0, x1 - x0, y1 - y0))
            rect.setBrush(QtGui.QBrush(fill))
            rect.setPen(pen)
            rect.setZValue(10 + index)
            details = "\n".join(f"{key}: {value}" for key, value in region.details.items())
            rect.setToolTip(f"{region.name}\n{details}" if details else region.name)
            self.plot.addItem(rect)

        assignment = self.current_assignment()
        if assignment is not None and visible_regions:
            color = self._theme.color(ASSIGNMENT_CATEGORY, assignment)
            self.plot.plot([], [], pen=pg.mkPen(color, width=3), name=assignment)

        selected_pair_id = None
        if self._selected_requested_index is not None and 0 <= self._selected_requested_index < len(requested):
            selected_pair_id = requested[self._selected_requested_index].pair_id

        pairs: dict[str, list[tuple[float, float, RequestedConfiguration]]] = {}
        for index, item in enumerate(requested):
            x = x_map.to_plot(item.voltage_v)
            y = y_map.to_plot(item.current_a)
            if item.pair_id is not None:
                pairs.setdefault(item.pair_id, []).append((x, y, item))

        contrast_color = QtGui.QColor("#FFFFFF" if background.lightness() < 128 else "#111111")

        for pair_items in pairs.values():
            if len(pair_items) != 2:
                continue
            (x0, y0, first), (x1, y1, second) = pair_items
            pair_selected = first.pair_id == selected_pair_id
            line_color = QtGui.QColor(
                self._theme.color(ASSIGNMENT_CATEGORY, assignment)
                if first.supported and second.supported and assignment
                else "#EF5350"
            )

            halo = self.plot.plot(
                [x0, x1],
                [y0, y1],
                pen=pg.mkPen(contrast_color, width=7 if pair_selected else 5),
            )
            halo.setZValue(800)
            connector = self.plot.plot(
                [x0, x1],
                [y0, y1],
                pen=pg.mkPen(line_color, width=5 if pair_selected else 3),
            )
            connector.setZValue(810)

        for index, item in enumerate(requested):
            selected = index == self._selected_requested_index or (selected_pair_id is not None and item.pair_id == selected_pair_id)
            bus_color = QtGui.QColor(
                self._theme.color(ASSIGNMENT_CATEGORY, assignment)
                if assignment
                else self.palette().highlight().color()
            )
            fill_color = bus_color if item.supported else QtGui.QColor("#EF5350")
            x = x_map.to_plot(item.voltage_v)
            y = y_map.to_plot(item.current_a)

            if item.marker == "pulse":
                outline_color = bus_color.darker(150).darker(115)
                pen = QtGui.QPen(outline_color)
                pen.setCosmetic(True)
                pen.setWidth(4 if selected else 3)
                pen.setStyle(_dash_line_style())
                symbol = "s"
            else:
                pen = QtGui.QPen(bus_color)
                pen.setCosmetic(True)
                pen.setWidth(3 if selected else 2)
                pen.setStyle(_solid_line_style())
                symbol = "o"

            marker_size = 16 if selected else 12
            halo_pen = QtGui.QPen(contrast_color)
            halo_pen.setCosmetic(True)
            halo_pen.setWidth(4 if selected else 3)
            halo_pen.setStyle(_solid_line_style())
            marker_halo = pg.ScatterPlotItem(
                [x],
                [y],
                size=marker_size + 6,
                symbol=symbol,
                brush=pg.mkBrush(0, 0, 0, 0),
                pen=halo_pen,
            )
            marker_halo.setZValue(1090 if selected else 990)
            self.plot.addItem(marker_halo)

            marker = pg.ScatterPlotItem(
                [x],
                [y],
                size=marker_size,
                symbol=symbol,
                brush=pg.mkBrush(fill_color),
                pen=pen,
            )
            label = item.label or f"Configuration {index + 1}"
            tooltip = item.tooltip or label
            marker.setToolTip(
                f"{tooltip}\nVoltage: {format_quantity(item.voltage_v, 'V')}"
                f"\nCurrent: {format_quantity(item.current_a, 'A')}"
            )
            marker.setZValue(1100 if selected else 1000)
            self.plot.addItem(marker)

        extent_x = max(x_map.extent, 1.0)
        extent_y = max(y_map.extent, 1.0)
        self.plot.setXRange(-extent_x * 1.05, extent_x * 1.05, padding=0)
        self.plot.setYRange(-extent_y * 1.05, extent_y * 1.05, padding=0)


class PowerEnvelopeGridView(QtWidgets.QScrollArea):
    """Show the buses used by one test plan as independent envelope plots."""

    COLUMNS = 2

    def __init__(self, theme: ColorTheme, parent=None) -> None:
        super().__init__(parent)
        self._theme = theme
        self._resources: Mapping[str, PowerResourceDefinition] = {}
        self._requests_by_assignment: dict[str, tuple[RequestedConfiguration, ...]] = {}
        self._selected_by_assignment: dict[str, int | None] = {}
        self.plots_by_assignment: dict[str, PowerEnvelopeComparisonView] = {}

        self.setWidgetResizable(True)
        self._content = QtWidgets.QWidget()
        self._layout = QtWidgets.QGridLayout(self._content)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(10)
        self.setWidget(self._content)

    def set_power_resources(self, resources: Mapping[str, PowerResourceDefinition]) -> None:
        self._resources = resources
        self._rebuild()

    def set_configurations(
        self,
        requests_by_assignment: Mapping[str, Sequence[RequestedConfiguration]],
        *,
        selected_by_assignment: Mapping[str, int | None] | None = None,
    ) -> None:
        self._requests_by_assignment = {
            assignment: tuple(requests)
            for assignment, requests in requests_by_assignment.items()
        }
        self._selected_by_assignment = dict(selected_by_assignment or {})
        self._rebuild()

    def assignments(self) -> tuple[str, ...]:
        return tuple(self.plots_by_assignment)

    def _rebuild(self) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.plots_by_assignment.clear()

        available = {region.assignment for region in regions_from_power_resources(self._resources)}
        assignments = [assignment for assignment in self._requests_by_assignment if assignment in available]
        assignments.sort(key=_assignment_sort_key)

        for index, assignment in enumerate(assignments):
            frame = QtWidgets.QGroupBox(assignment)
            frame_layout = QtWidgets.QVBoxLayout(frame)
            plot = PowerEnvelopeComparisonView(self._theme)
            plot.set_bus_selector_visible(False)
            plot.set_power_resources(self._resources)
            plot.set_assignment(assignment)
            plot.set_requested_configurations(
                self._requests_by_assignment.get(assignment, ()),
                selected_index=self._selected_by_assignment.get(assignment),
            )
            frame_layout.addWidget(plot)
            self.plots_by_assignment[assignment] = plot
            self._layout.addWidget(frame, index // self.COLUMNS, index % self.COLUMNS)

        if not assignments:
            message = QtWidgets.QLabel("No powered DC buses with hardware envelopes are used by this test plan.")
            message.setWordWrap(True)
            self._layout.addWidget(message, 0, 0)


def _assignment_sort_key(assignment: str) -> tuple[int, int, str]:
    upper = assignment.upper()
    if upper.startswith("DC") and upper[2:].isdigit():
        return 0, int(upper[2:]), upper
    return 1, 0, upper


def requested_configuration_from_bias(
    bias: Mapping[str, Any],
    *,
    assignment: str,
    label: str,
) -> RequestedConfiguration | None:
    level = bias.get("level", bias.get("bias_level"))
    if level is None:
        return None
    compliance = bias.get("compliance_limit", bias.get("compliance", 0.0))
    compliance = 0.0 if compliance is None else float(compliance)
    mode = str(bias.get("mode", bias.get("source_mode", "voltage"))).lower()
    if mode in {"ground", "floating"}:
        return None
    if mode == "current":
        voltage, current = compliance, float(level)
    else:
        voltage, current = float(level), compliance
    return RequestedConfiguration(
        voltage_v=voltage,
        current_a=current,
        assignment=assignment,
        supported=True,
        label=label,
        tooltip=label,
    )
