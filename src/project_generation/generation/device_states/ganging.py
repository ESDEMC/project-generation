from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import Any


BiasSpec = Mapping[str, Any]


def merge_bias_specs(*specs: BiasSpec) -> dict[str, Any]:
    """Merge compatible partial bias specifications.

    Missing fields are filled from the other specs. ``compliance_limit`` is a
    capacity requirement, so ganged groups use the largest requested limit.
    Other conflicting concrete values make the specs incompatible.
    """
    merged: dict[str, Any] = {}
    for spec in specs:
        for key, value in spec.items():
            if key == "compliance_limit":
                if key not in merged:
                    merged[key] = value
                else:
                    merged[key] = max(float(merged[key]), float(value))
                continue

            if key in merged and merged[key] != value:
                raise ValueError(f'conflicting bias field "{key}": {merged[key]!r} != {value!r}')
            merged[key] = value
    return merged


def bias_specs_are_compatible(left: BiasSpec, right: BiasSpec) -> bool:
    try:
        merge_bias_specs(left, right)
    except ValueError:
        return False
    return True


class GangingPolicy(ABC):
    name: str

    @abstractmethod
    def gang(self, bias_specs: Mapping[str, BiasSpec]) -> tuple[tuple[str, ...], ...]:
        """Partition groups into gangs that may share one power domain."""
        raise NotImplementedError


class NoGangingPolicy(GangingPolicy):
    name = "none"

    def gang(self, bias_specs: Mapping[str, BiasSpec]) -> tuple[tuple[str, ...], ...]:
        return tuple((group_name,) for group_name in bias_specs)


class SameVoltageGangingPolicy(GangingPolicy):
    name = "same_voltage"

    def gang(self, bias_specs: Mapping[str, BiasSpec]) -> tuple[tuple[str, ...], ...]:
        gangs: list[list[str]] = []
        gang_specs: list[dict[str, Any]] = []

        for group_name, bias_spec in bias_specs.items():
            for index, gang_spec in enumerate(gang_specs):
                if not self.compatible(gang_spec, bias_spec):
                    continue
                gangs[index].append(group_name)
                gang_specs[index] = merge_bias_specs(gang_spec, bias_spec)
                break
            else:
                gangs.append([group_name])
                gang_specs.append(dict(bias_spec))

        return tuple(tuple(gang) for gang in gangs)

    @staticmethod
    def compatible(left: BiasSpec, right: BiasSpec) -> bool:
        if not bias_specs_are_compatible(left, right):
            return False

        left_mode = str(left.get("mode", "VOLTAGE" if "level" in left else "")).upper()
        right_mode = str(right.get("mode", "VOLTAGE" if "level" in right else "")).upper()
        if left_mode and right_mode and left_mode != right_mode:
            return False

        if left_mode in {"GROUND", "FLOATING"} or right_mode in {"GROUND", "FLOATING"}:
            return left_mode == right_mode

        left_level = left.get("level")
        right_level = right.get("level")
        return left_level is None or right_level is None or left_level == right_level


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
