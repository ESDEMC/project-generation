import enum
import typing
import uuid
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np
from dataclasses_json import DataClassJsonMixin

LeakagePlanID = uuid.UUID

SourceMode = typing.Literal["voltage", "current"]

class SmuSourceMode(enum.StrEnum):
    VOLTAGE = "Voltage"
    CURRENT = "Current"


class SensorModes(enum.StrEnum):
    TWO_WIRE = "2 Wire"
    FOUR_WIRE = "4 Wire"


class SourceType(enum.StrEnum):
    VOLTAGE = "voltage"
    CURRENT = "current"


class LeakageSources(enum.Enum):
    SOURCE_VOLTAGE = "Source Voltage"
    SOURCE_CURRENT = "Source Current"


class SweepOrder(enum.StrEnum):
    ASCENDING_MAGNITUDE = "N(Small to Large) -> P(Small to Large)"
    LOW_HIGH = "Low -> High"
    HIGH_LOW = "High -> Low"
    LOW_HIGH_LOW = "Dual (Low -> High -> Low)"
    HIGH_LOW_HIGH = "Dual (High -> Low -> High)"


@dataclass(kw_only=True, frozen=True)
class DCSweepData:
    data_id: uuid.UUID = field(default_factory=uuid.uuid4)
    timestamp: datetime = field(default_factory=datetime.now)
    voltage: np.ndarray = field(default_factory=lambda: np.array([]))
    current: np.ndarray = field(default_factory=lambda: np.array([]))
    source_type: LeakageSources | SourceType = SourceType.VOLTAGE


@dataclass(frozen=False, kw_only=True)
class StaticIv:
    is_enabled: bool = False
    upper_percent_tolerance: float | None = 10.0
    upper_value_tolerance: float | None = 1e-6
    lower_percent_tolerance: float | None = 10.0
    lower_value_tolerance: float | None = 1e-6
    pop_up_on_failure: bool = True
    reference: DCSweepData | None = None


@dataclass(frozen=False, kw_only=True)
class ContinuityCheck:
    is_enabled: bool = False
    upper_bound: float | None = None
    lower_bound: float | None = None
    pop_up_on_failure: bool = True


@dataclass(frozen=True)
class LeakageConfig:
    source_mode: SmuSourceMode
    sorting_mode: SweepOrder
    compliance_limit: float
    settle_time: float
    nplc: float = 1.0
    sensor_mode: SensorModes = SensorModes.TWO_WIRE


@dataclass(kw_only=True)
class Sweep:
    enabled: bool | None
    log: bool | None
    start: float | None
    stop: float | None
    step_size: float | None
    n_steps: int | None


@dataclass(kw_only=True)
class LeakagePlan:
    leakage_plan_id: uuid.UUID
    name: str
    config: LeakageConfig
    static_iv: StaticIv = field(default_factory=StaticIv)
    continuity_check: ContinuityCheck = field(default_factory=ContinuityCheck)
    levels: list[float | None] = field(default_factory=list)
    sweeps: list[Sweep] = field(default_factory=list)


@dataclass(frozen=True)
class LeakageConfigFile(DataClassJsonMixin):
    leakage_file_id: uuid.UUID = field(default_factory=uuid.uuid4)
    leakage_plans: list[LeakagePlan] = field(default_factory=list)

    def save(self, path):
        with open(path, "w") as f:
            f.write(self.to_json(indent=4))

    @classmethod
    def load(cls, path):
        with open(path, "r") as f:
            text = f.read()
            return cls.from_json(text)
