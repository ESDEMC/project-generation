import typing
import uuid
from dataclasses import dataclass, field

from dataclasses_json import DataClassJsonMixin
from .enums import LuTestType, SourceMode, DevicePinType, SweepMethod, MatrixAssignment

DeviceID = str
Designator = str
PinID = str
TestGroupID = str
PinGroupID = str


@dataclass
class Line:
    x1: float
    y1: float
    x2: float
    y2: float
    width: float = 0


@dataclass
class Rect:
    x: float
    y: float
    width: float
    height: float


@dataclass
class Pen:
    color: str
    width: float
    style: int
    cap_style: int


@dataclass
class Arc:
    x: float
    y: float
    w: float
    h: float
    angle: int
    start_angle: int = 0


@dataclass
class PackageData:
    rects: list[Rect] = field(default_factory=list)
    lines: list[Line] = field(default_factory=list)
    pens: list[Pen] = field(default_factory=list)
    arcs: list[Arc] = field(default_factory=list)


@dataclass(kw_only=True)
class PinGroup(DataClassJsonMixin):
    pin_group_id: uuid.UUID = field(default_factory=lambda: uuid.uuid4())
    name: str
    pins: list[uuid.UUID] = field(default_factory=list)
    group_type: DevicePinType = DevicePinType.NC
    matrix_assignment: MatrixAssignment = MatrixAssignment.FLOAT
    float_during_preconditioning: bool = False
    is_bias_group: bool = False


@dataclass(kw_only=True)
class TestGroup(PinGroup):
    pulse_width: float = 0.010


@dataclass(kw_only=True)
class SignalTestGroup(TestGroup):
    group_type: DevicePinType = DevicePinType.INPUT
    i_test_bias_source_mode: SourceMode = "current"
    signal_test_type: LuTestType = LuTestType.I_TEST
    compliance_limit: float | None = None
    v_max_op: float | None = None
    v_min_op: float | None = None
    positive_stress_bias_current: float | None = None
    positive_stress_bias_voltage: float | None = None
    positive_injection_current: list[float] | None = field(default_factory=list)
    positive_injection_voltage: list[float] | None = field(default_factory=list)
    negative_stress_bias_current: float | None = None
    negative_stress_bias_voltage: float | None = None
    negative_injection_current: list[float] | None = field(default_factory=list)
    negative_injection_voltage: list[float] | None = field(default_factory=list)
    sweep_method: SweepMethod = SweepMethod.SWEEP_SOURCE


@dataclass(kw_only=True)
class SupplyTestGroup(TestGroup):
    group_type: DevicePinType = DevicePinType.POWER
    compliance_limit: float | None = None
    v_max_sup: float | None = None
    stress_bias_current: float | None = None
    stress_bias_voltage: float | None = None
    injection_current: list[float] | None = None
    injection_voltage: list[float] | None = None
    stress_all: bool = True
    sweep_method: SweepMethod = SweepMethod.SWEEP_SOURCE


@dataclass(kw_only=True)
class DutPin:
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    designator: str
    """Pin designator"""
    pin_name: str
    """Pin name"""
    description: str | None = None
    parameters: dict[str, str] = field(kw_only=True, default_factory=dict)

    @property
    def pin_id(self):
        return self.id


@dataclass(kw_only=True, eq=False)
class PinDescriptor(DataClassJsonMixin):
    pin_id: PinID
    designator: str
    name: str


@dataclass(kw_only=True, frozen=True, eq=False)
class TestGroupDescriptor(DataClassJsonMixin):
    group_id: TestGroupID
    name: str
    group_type: DevicePinType
    pins: list[PinDescriptor] = field(default_factory=list)


@dataclass(kw_only=True, eq=False)
class DeviceDescriptor(DataClassJsonMixin):
    device_id: DeviceID
    device_name: str
    pins: list[PinDescriptor]
    test_groups: list[TestGroupDescriptor]

    def get_pin(self, pin_id):
        for pin in self.pins:
            if str(pin.pin_id) == str(pin_id):
                return pin
        raise ValueError(f"Pin {pin_id} not found")


@dataclass
class Dut(DataClassJsonMixin):
    device_id: uuid.UUID = field(default_factory=uuid.uuid4, init=False)
    name: str = ""
    pins: list[DutPin] = field(default_factory=list)
    package: PackageData = field(default_factory=PackageData)
    device_info: dict[str, typing.Any] = field(default_factory=dict)
    pin_groups: list[SupplyTestGroup | SignalTestGroup | PinGroup] = field(default_factory=list)

    def save(self, path):
        with open(path, "w") as f:
            f.write(self.to_json(indent=2))

    @classmethod
    def load(cls, path):
        with open(path, "r") as f:
            text = f.read()
            return cls.from_json(text)

    def add_pin_group(self, group) -> PinGroupID:
        known = {pin.pin_id for pin in self.pins}
        unknown = [pin for pin in group.pins if pin not in known]
        if unknown:
            raise ValueError(f"Unknown DUT pins in group {group.name!r}: {unknown}")
        self.pin_groups.append(group)
        return group.pin_group_id

    def descriptor(self) -> DeviceDescriptor:
        by_id = {
            pin.pin_id: PinDescriptor(pin_id=pin.pin_id, designator=pin.designator, name=pin.pin_name)
            for pin in self.pins
        }
        return DeviceDescriptor(
            device_id=self.device_id,
            device_name=self.name,
            pins=list(by_id.values()),
            test_groups=[
                TestGroupDescriptor(
                    group_id=group.pin_group_id,
                    name=group.name,
                    group_type=group.group_type,
                    pins=[by_id[pin_id] for pin_id in group.pins],
                )
                for group in self.pin_groups
            ],
        )
