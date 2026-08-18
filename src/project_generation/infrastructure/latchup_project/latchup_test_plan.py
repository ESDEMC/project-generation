import dataclasses
import pathlib
import typing
import uuid
from dataclasses import dataclass, field

from dataclasses_json import DataClassJsonMixin

from .dut import PinGroup, PinDescriptor, TestGroupDescriptor, DeviceDescriptor
from .enums import SourceMode, MatrixAssignment, LuTestType, PolarityEnum, LogicLevelEnum

PinID = str
TestGroupID = str
DeviceID = str
ChannelID = str
DeviceStateID = str
PowerDomainID = str
TestPlanID = str


@dataclass(frozen=True, kw_only=True)
class LatchUpBiasParameters:
    bias_level: float
    source_mode: SourceMode
    compliance_limit: float


@dataclass(slots=True, frozen=True)
class LatchUpPulseParameters:
    base: float
    peak: float
    compliance_limit: float
    source_mode: SourceMode
    pulse_width: float = 0.010
    pulse_delay: float = 0.0


@dataclasses.dataclass(kw_only=True, frozen=True, slots=True)
class StressParameters:
    bias_parameters: LatchUpBiasParameters
    pulse_parameters: LatchUpPulseParameters
    pre_stress_delay: float = 0.005
    """(seconds)"""
    post_stress_delay: float = 0.005
    """(seconds)"""
    measure_duration: float = 0.005
    """(seconds)"""


@dataclass(frozen=True)
class TimingInfo:
    delay: float = 0.0
    settle_time: float = 0.0
    reference: MatrixAssignment | None = None


@dataclass(kw_only=True)
class PowerSupplyTiming:
    channel_id: ChannelID = field(default_factory=uuid.uuid4)
    matrix_assignment: MatrixAssignment
    power_on_timing: TimingInfo = field(default_factory=TimingInfo)
    power_off_timing: TimingInfo = field(default_factory=TimingInfo)


@dataclass(kw_only=True, frozen=True)
class MeasurementTiming:
    measurement_duration: float = 0.1
    pre_stress_delay: float = 0.005
    post_stress_delay: float = 0.005


@dataclass(kw_only=True)
class PowerSequence(DataClassJsonMixin):
    power_sequence_id: uuid.UUID = field(default_factory=uuid.uuid4, init=False)
    timing: list[PowerSupplyTiming] = field(default_factory=list)
    measurement_timing: MeasurementTiming = MeasurementTiming()

    def add_channel(
        self,
        matrix_assignment,
        channel_id: ChannelID = None,
        power_on_timing: TimingInfo = None,
        power_off_timing: TimingInfo = None,
    ) -> typing.Self:
        self.timing.append(
            PowerSupplyTiming(
                channel_id=channel_id or ChannelID(str(uuid.uuid4())),
                matrix_assignment=matrix_assignment,
                power_on_timing=power_on_timing or TimingInfo(),
                power_off_timing=power_off_timing or TimingInfo(),
            )
        )
        return self


@dataclass(kw_only=True)
class PowerDomain:
    power_domain_id: PowerDomainID = field(default_factory=uuid.uuid4)
    matrix_assignment: MatrixAssignment
    test_groups: list[TestGroupDescriptor] = field(default_factory=list)
    bias_config: LatchUpBiasParameters | None = None
    power_on_timing_info: TimingInfo = field(default_factory=TimingInfo)
    power_off_timing_info: TimingInfo = field(default_factory=TimingInfo)


@dataclass(kw_only=True)
class DeviceState:
    device_state_id: DeviceStateID = field(default_factory=uuid.uuid4)
    power_domains: list[PowerDomain] = field(default_factory=list)
    ground_pins: list[PinDescriptor] = field(default_factory=list)
    floating_pins: list[PinDescriptor] = field(default_factory=list)
    measurement_timing: MeasurementTiming = MeasurementTiming()

    def validate(self):
        for domain in self.power_domains:
            assert isinstance(domain, PowerDomain)
        for pin in self.ground_pins:
            assert isinstance(pin, PinDescriptor)
        for pin in self.floating_pins:
            assert isinstance(pin, PinDescriptor)

        assert isinstance(self.measurement_timing, MeasurementTiming)

    def power_sequence(self) -> PowerSequence:
        power_sequence = PowerSequence(measurement_timing=self.measurement_timing)
        for domain in self.power_domains:
            power_sequence.add_channel(
                matrix_assignment=domain.matrix_assignment,
                power_on_timing=domain.power_on_timing_info,
                power_off_timing=domain.power_off_timing_info,
            )
        return power_sequence

    def set_power_sequence(self, power_sequence: PowerSequence):
        self.measurement_timing = power_sequence.measurement_timing
        for domain in self.power_domains:
            for timing in power_sequence.timing:
                if timing.matrix_assignment == domain.matrix_assignment:
                    domain.power_on_timing_info = timing.power_on_timing
                    domain.power_off_timing_info = timing.power_off_timing
                    break



@dataclasses.dataclass(kw_only=True)
class TemperatureControl:
    enabled: bool = True
    temperature: float = 25
    soak_time: float = 0.0
    factor: float = 1.0
    offset: float = 0.0
    start_tolerance: float = 10.0
    cool_temperature: float = 24.0
    timeout: float = 900


@dataclasses.dataclass(kw_only=True, frozen=True)
class StressPlan:
    stresses: list[tuple[TestGroupDescriptor, list[StressParameters]]] = dataclasses.field(default_factory=list)

    def set_stress_parameters(self, stress_group: TestGroupDescriptor, stress_parameters: list[StressParameters]):
        for i, (group, parameters) in enumerate(self.stresses.copy()):
            if group == stress_group:
                self.stresses[i] = (stress_group, stress_parameters.copy())
                break
        else:
            self.stresses.append((stress_group, stress_parameters.copy()))


@dataclass(kw_only=True)
class LatchUpTestPlan(DataClassJsonMixin):
    test_plan_id: uuid.UUID = field(default_factory=uuid.uuid4)
    name: str
    test_groups: list[PinGroup]
    _stresses: list[tuple[TestGroupDescriptor, list[StressParameters]]] = field(default_factory=list)
    test_pins: list[PinID]
    device_info: DeviceDescriptor
    power_sequence: PowerSequence = dataclasses.field(default_factory=PowerSequence)
    test_type: LuTestType = LuTestType.SIGNAL_TEST
    polarity: PolarityEnum = PolarityEnum.POSITIVE
    device_state: DeviceState = field(default_factory=DeviceState)
    logic_level: LogicLevelEnum = LogicLevelEnum.HIGH
    ground_connection: MatrixAssignment = MatrixAssignment.GND
    temperature_control: TemperatureControl = field(default_factory=TemperatureControl)
    cool_time: float = 0.0
    metadata: dict = field(default_factory=dict)

    @property
    def stress_plan(self):
        return StressPlan(stresses=self._stresses)

    def to_dict(self, **kwargs) -> dict:
        kwargs.setdefault("encode_json", True)
        data: dict = super().to_dict(**kwargs)
        data.pop("test_plan_id", None)

        get_pin_info = get_pin_info_from_device_descriptor(self.device_info)

        convert_pin_list(data, "test_pins", get_pin_info)
        for test_group in data["test_groups"]:
            convert_pin_list(test_group, "pins", get_pin_info)
        return data

    def save(self, file_path):
        file_path = pathlib.Path(file_path)

        if not file_path.parent.exists():
            file_path.parent.mkdir(parents=True, exist_ok=True)

        data = self.to_dict()

        with open(file_path, "w") as file:
            json.dump(data, file, indent=2, default=str)  # type: ignore


def get_pin_info_from_device_descriptor(device: DeviceDescriptor):

    def inner(pin_id: PinID):
        return device.get_pin(pin_id).to_dict(encode_json=True)

    return inner


def convert_pin_list(data, key, method):
    data[key] = [method(pin) for pin in data[key]]
