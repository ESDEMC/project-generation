import pathlib

from dataclasses import field, dataclass
import uuid

from dataclasses_json import DataClassJsonMixin

from .latchup_test_plan import LatchUpBiasParameters
from .enums import MatrixAssignment


FunctionalTestID = uuid.UUID
PinGroupID = uuid.UUID
LeakagePlanID = uuid.UUID


@dataclass
class LeakageBiasGroup:
    test_group: PinGroupID | None
    test_group_name: str
    power_supply: MatrixAssignment
    bias_config: LatchUpBiasParameters


@dataclass(kw_only=True)
class LeakageTestPlan(DataClassJsonMixin):
    name: str
    enabled: bool = True
    test_groups: list[PinGroupID] = field(default_factory=list)
    ground_groups: list[PinGroupID] = field(default_factory=list)
    leakage_plan: LeakagePlanID | None = None
    leakage_channel: MatrixAssignment = None
    ground_connect: MatrixAssignment | None = MatrixAssignment.GND
    bias_groups: list[LeakageBiasGroup] = field(default_factory=list)
    source_psu: MatrixAssignment = None


@dataclass(kw_only=True)
class LeakageFunctionalTestPlan(DataClassJsonMixin):
    functional_test_id: FunctionalTestID = field(default_factory=lambda: uuid.uuid4())
    name: str
    leakage_tests: list[LeakageTestPlan]
    reference_path: pathlib.Path | None = None
    reference_enabled: bool = False

    def save(self, path):
        with open(path, "w") as f:
            f.write(self.to_json(indent=4))

    @classmethod
    def load(cls, path):
        with open(path, "r") as f:
            text = f.read()
            return cls.from_json(text)
