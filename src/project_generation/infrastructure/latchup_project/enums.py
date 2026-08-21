import typing
import enum


__all__ = [
    "LuTestType",
    "DevicePinType",
    "PolarityEnum",
    "LogicLevelEnum",
    "SignalPinType",
    "SupplyPinType",
    "SourceMode",
    "SweepMethod",
    "SignalTestType",
    "SupplyTestType",
    "BridgeMode",
    "BridgeCalculationMode",
    "SourceModeEnum",
    "SensorModes",
    "MatrixAssignment",
    "SweepOrder",
    "SensorMode",
    "SmuSourceMode",
]


T = typing.TypeVar("T")
SourceMode = typing.Literal["voltage", "current"]


def measure_mode(source_mode: SourceMode) -> SourceMode:
    if source_mode not in ["voltage", "current"]:
        raise ValueError(f"Invalid source mode: {source_mode}")
    return {"voltage": "current", "current": "voltage"}[source_mode]  # type: ignore[return-value]


class SourceModeEnum(enum.StrEnum):
    VOLTAGE = "Voltage"
    CURRENT = "Current"

    @classmethod
    def from_str(cls, value: str) -> typing.Self:
        try:
            return cls(value.lower())
        except ValueError:
            raise ValueError(f"Invalid source mode: {value}")

    def to_str(self) -> str:
        """Convert the enum to a string."""
        return str(self)

    def is_voltage(self) -> bool:
        return self == SourceModeEnum.VOLTAGE

    def is_current(self) -> bool:
        return self == SourceModeEnum.CURRENT

    def choose(self, voltage: T, current: T) -> T:
        if self == self.VOLTAGE:
            return voltage
        else:
            return current

    def other(self) -> typing.Self:
        if self.is_voltage():
            return SourceModeEnum.CURRENT
        elif self.is_current():
            return SourceModeEnum.VOLTAGE
        else:
            raise ValueError(f"Invalid source mode: {self}")

    def __invert__(self):
        """Invert the source mode."""
        return self.other()

    def display(self) -> str:
        """Display the source mode in a user-friendly format."""
        return self.value.title()

    @classmethod
    def from_display(cls, display_name: str) -> typing.Self:
        """Create a SourceModeEnum from a display name."""
        try:
            return cls[display_name.upper()]
        except KeyError:
            raise ValueError(f"Invalid display name for SourceModeEnum: {display_name}")


class MatrixAssignment(enum.Enum):
    TERM_A = "TERM_A"
    TERM_B = "TERM_B"
    EXT1 = "EXT1"
    EXT2 = "EXT2"
    EXT3 = "EXT3"
    GND = "GND"
    FLOAT = "FLOAT"
    DC1 = "DC1"
    DC2 = "DC2"
    DC3 = "DC3"
    DC4 = "DC4"
    DC5 = "DC5"
    DC6 = "DC6"
    DC7 = "DC7"
    DC8 = "DC8"
    DC9 = "DC9"
    DC10 = "DC10"
    DC11 = "DC11"
    DC12 = "DC12"
    DC13 = "DC13"
    DC14 = "DC14"
    DC15 = "DC15"
    DC16 = "DC16"
    DC17 = "DC17"
    DC18 = "DC18"
    DC19 = "DC19"
    DC20 = "DC20"
    DC21 = "DC21"
    DC22 = "DC22"
    DC23 = "DC23"
    DC24 = "DC24"
    DC25 = "DC25"
    DC26 = "DC26"
    DC27 = "DC27"
    DC28 = "DC28"
    DC29 = "DC29"
    DC30 = "DC30"
    DC31 = "DC31"
    DC32 = "DC32"

    @classmethod
    def buses(cls) -> "list[MatrixAssignment]":
        return [v for v in cls if v.name.startswith("DC")]

    @classmethod
    def from_bus_index(cls, bus_index: int) -> "MatrixAssignment":
        return cls(f"DC{bus_index + 1}")

    def as_bus_index(self):
        return int(self)

    def __int__(self):
        return self.bus_number() - 1

    def bus_number(self) -> int:
        try:
            return int(self.name.removeprefix("DC"))
        except ValueError:
            raise ValueError(f"Invalid value for MatrixAssignment: {self.value}")

    def display(self):
        if self.is_dc():
            return self.value.replace("DC", "Bus ")
        elif "term" in self.value.lower():
            return self.value.replace("TERM_", "Terminal ")
        elif "ext" in self.value.lower():
            return self.value.replace("EXT", "EXT ")
        elif self.is_ground():
            return "Ground"
        elif self.is_floating():
            return "Floating"
        else:
            return self.name.title()

    @classmethod
    def from_display(cls, display):
        for item in cls:
            if item.display() == display:
                return item
        return None

    @classmethod
    def from_str(cls, text):
        for item in cls:
            if str(item) == text:
                return item
        raise ValueError(f"Invalid value for MatrixAssignment: {text}")

    def is_mux(self):
        return self in [self.TERM_A, self.EXT1, self.EXT2, self.EXT3]

    def is_external(self):
        return self in [self.EXT1, self.EXT2, self.EXT3]

    def is_dc(self):
        return self in self.buses()

    def is_floating(self):
        return self == self.FLOAT

    def is_ground(self):
        return self in [self.GND, self.TERM_B]

    def __lt__(self, other):
        l = list(self.__class__)
        if other is None:
            return False

        return l.index(self) < l.index(other)


class DevicePinType(enum.StrEnum):
    INPUT = "INPUT"
    OUTPUT = "OUTPUT"
    IO = "IO"
    POWER = "POWER"
    GROUND = "GROUND"
    NC = "NC"
    CLOCK = "CLOCK"

    def is_signal(self):
        return self in [DevicePinType.INPUT, DevicePinType.OUTPUT, DevicePinType.IO]

    def is_input(self):
        return self in [DevicePinType.INPUT]

    def is_supply(self):
        return self in [DevicePinType.POWER]

    def is_power(self):
        return self in [DevicePinType.POWER]

    def display(self):
        return {
            self.INPUT: "Input",
            self.OUTPUT: "Output",
            self.IO: "IO",
            self.POWER: "Power",
            self.GROUND: "Ground",
            self.NC: "NC",
            self.CLOCK: "Clock",
        }[self]

    @classmethod
    def from_display(cls, param):
        return cls(param.lower())

    def is_floating(self):
        return self in [DevicePinType.OUTPUT, DevicePinType.NC, DevicePinType.CLOCK]

    def is_ground(self):
        return self == DevicePinType.GROUND

    def is_output(self):
        return self == DevicePinType.OUTPUT


SignalPinType = typing.Literal[DevicePinType.INPUT, DevicePinType.OUTPUT, DevicePinType.IO]
SupplyPinType = typing.Literal[DevicePinType.POWER, DevicePinType.GROUND]


class LuTestType(enum.StrEnum):
    SUPPLY_TEST = "Supply Test"
    I_TEST = "I-Test"
    E_TEST = "E-Test"
    IDD_TEST = "IDD-Test"
    SIGNAL_TEST = "Signal Test"
    SIGNAL_IDD_TEST = "Signal IDD-Test"
    SUPPLY_IDD_TEST = "Supply IDD-Test"

    def is_signal(self):
        return self in [self.E_TEST, self.I_TEST, self.SIGNAL_TEST, self.SIGNAL_IDD_TEST]

    def is_supply(self):
        return self in [self.SUPPLY_TEST, self.SUPPLY_IDD_TEST]

    def is_idd(self):
        return self in [self.IDD_TEST, self.SIGNAL_IDD_TEST, self.SUPPLY_IDD_TEST]

    def is_i_test(self):
        return self == self.I_TEST

    def source_mode(self) -> SourceMode:
        if self == LuTestType.I_TEST:
            return "current"
        elif self == LuTestType.E_TEST:
            return "voltage"
        elif self == LuTestType.SUPPLY_TEST:
            return "voltage"
        else:
            raise ValueError(f"Invalid test type: {self}")

    def get_source_and_limit(self, voltage: T, current: T) -> tuple[T, T]:
        if self.source_mode() == "voltage":
            return voltage, current
        else:
            return current, voltage

    def display(self):
        return self.value

    @classmethod
    def from_display(cls, display_name: str) -> typing.Self:
        for member in cls:
            if member.display() == display_name:
                return member
        else:
            raise ValueError(f"Invalid display name for LuTestType: {display_name}")


SignalTestType = typing.Literal[LuTestType.I_TEST, LuTestType.E_TEST]
SupplyTestType = typing.Literal[LuTestType.SUPPLY_TEST]


class PolarityEnum(enum.StrEnum):
    POSITIVE = "positive"
    NEGATIVE = "negative"

    def choose(self, positive: T, negative: T) -> T:
        if self == self.POSITIVE:
            return positive
        else:
            return negative


class LogicLevelEnum(enum.StrEnum):
    HIGH = "High"
    LOW = "Low"

    def choose(self, high: T, low: T) -> T:
        if self == self.HIGH:
            return high
        else:
            return low


class SweepMethod(enum.StrEnum):
    SWEEP_SOURCE = "Sweep Source"
    SWEEP_LIMIT = "Sweep Limit"
    SWEEP_VOLTAGE = "Sweep Voltage"
    SWEEP_CURRENT = "Sweep Current"
    TWO_D_ARRAY = "2D-Array"

    def fixup(self, a: list | None, b: list | None):
        if self in [self.SWEEP_SOURCE, self.SWEEP_VOLTAGE]:
            return a, (b or [None])[0]
        elif self in [self.SWEEP_LIMIT, self.SWEEP_CURRENT]:
            return (a or [None])[0], b
        else:
            return a, b

    def is_voltage_sweep(self, source_mode: SourceMode):
        source_mode = SourceModeEnum(source_mode)
        return any(
            [
                self == self.SWEEP_SOURCE and source_mode.is_voltage(),
                self == self.SWEEP_LIMIT and source_mode.is_current(),
                self == self.SWEEP_VOLTAGE,
                self == self.TWO_D_ARRAY,
            ]
        )

    def is_current_sweep(self, source_mode: SourceMode):
        source_mode = SourceModeEnum(source_mode)
        return any(
            [
                self == self.SWEEP_SOURCE and source_mode.is_current(),
                self == self.SWEEP_LIMIT and source_mode.is_voltage(),
                self == self.SWEEP_CURRENT,
                self == self.TWO_D_ARRAY,
            ]
        )


class BridgeMode(enum.StrEnum):
    SERIES = "series"
    PARALLEL = "parallel"

    def calculate_max_voltage(self, *max_voltage):
        if self == BridgeMode.SERIES:
            max_voltage = sum(max_voltage)
        elif self == BridgeMode.PARALLEL:
            max_voltage = min(max_voltage)
        else:
            raise ValueError(f"Invalid bridge type: {self}")

        return max_voltage

    def calculate_max_current(self, *max_current):
        if self == BridgeMode.SERIES:
            max_current = min(max_current)
        elif self == BridgeMode.PARALLEL:
            max_current = sum(max_current)
        else:
            raise ValueError(f"Invalid bridge type: {self}")

        return max_current

    def combine_voltage(self, *voltages):
        if self == BridgeMode.SERIES:
            return sum(voltages)
        elif self == BridgeMode.PARALLEL:
            return min(voltages, key=abs)
        else:
            raise ValueError(f"Invalid bridge type: {self}")

    def combine_current(self, *currents):
        if self == BridgeMode.SERIES:
            return min(currents, key=abs)
        elif self == BridgeMode.PARALLEL:
            return sum(currents)
        else:
            raise ValueError(f"Invalid bridge type: {self}")


class BridgeCalculationMode(enum.StrEnum):
    PROPORTIONAL = "proportional"
    INCREMENTAL = "incremental"


class SensorModes(enum.StrEnum):
    TWO_WIRE = "2 Wire"
    FOUR_WIRE = "4 Wire"

    def to_ti_mode(self):
        if self == self.TWO_WIRE:
            return "2_wire"
        elif self == self.FOUR_WIRE:
            return "4_wire"
        else:
            raise ValueError


class SweepOrder(enum.StrEnum):
    ASCENDING_MAGNITUDE = "N(Small to Large) -> P(Small to Large)"
    LOW_HIGH = "Low -> High"
    HIGH_LOW = "High -> Low"
    LOW_HIGH_LOW = "Dual (Low -> High -> Low)"
    HIGH_LOW_HIGH = "Dual (High -> Low -> High)"

