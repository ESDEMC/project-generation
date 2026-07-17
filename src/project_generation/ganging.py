from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Iterable, Mapping


@dataclass(frozen=True, kw_only=True)
class GangingCandidate:
    group_name: str
    bias: Mapping[str, Any]


@dataclass(frozen=True, kw_only=True)
class ExistingPowerAssignment:
    group_name: str
    assignment: str
    bias: Mapping[str, Any]


class GangingPolicy(ABC):
    name: str

    @abstractmethod
    def propose_assignment(
        self,
        candidate: GangingCandidate,
        existing_assignments: Iterable[ExistingPowerAssignment],
    ) -> str | None:
        raise NotImplementedError


class NoGangingPolicy(GangingPolicy):
    name = "none"

    def propose_assignment(
        self,
        candidate: GangingCandidate,
        existing_assignments: Iterable[ExistingPowerAssignment],
    ) -> str | None:
        return None


class SameVoltageGangingPolicy(GangingPolicy):
    name = "same_voltage"

    def propose_assignment(
        self,
        candidate: GangingCandidate,
        existing_assignments: Iterable[ExistingPowerAssignment],
    ) -> str | None:
        for existing in existing_assignments:
            if dict(existing.bias) == dict(candidate.bias):
                return existing.assignment
        return None


_POLICIES: dict[str, GangingPolicy] = {
    NoGangingPolicy.name: NoGangingPolicy(),
    SameVoltageGangingPolicy.name: SameVoltageGangingPolicy(),
}


def get_ganging_policy(name: str | None) -> GangingPolicy:
    policy_name = name or NoGangingPolicy.name
    try:
        return _POLICIES[policy_name]
    except KeyError as error:
        supported = ", ".join(sorted(_POLICIES))
        raise ValueError(f'unsupported ganging policy "{policy_name}"; supported policies: {supported}') from error
