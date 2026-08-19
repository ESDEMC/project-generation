import pathlib
from typing import Any, Mapping

import yaml

from project_generation.definition.models import PowerResourceDefinition
from project_generation.diagnostics import ProjectGenerationError
from project_generation.generation.hardware_domain import HardwarePowerResource, OperatingPoint, PowerSupplyCapabilities


def load_hardware_power_resources(path: str | pathlib.Path) -> dict[str, PowerResourceDefinition]:
    path = pathlib.Path(path)
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except OSError as error:
        raise ProjectGenerationError(
            f'Could not read hardware configuration "{path}"',
            code="hardware.read_failed",
            location="hardware.source",
        ) from error

    if not isinstance(data, Mapping):
        raise ProjectGenerationError(
            f'Hardware configuration must contain a top-level object: {path}',
            code="hardware.invalid_root",
            location="hardware.source",
        )

    power_supply = data.get("power_supply") or {}
    metadata = data.get("metadata") or {}
    connections = power_supply.get("hardware_connections") or [] if isinstance(power_supply, Mapping) else []
    metadata_entries = metadata.get("power_supply") or [] if isinstance(metadata, Mapping) else []

    connection_by_assignment: dict[str, Mapping[str, Any]] = {}
    for index, connection in enumerate(connections):
        if not isinstance(connection, Mapping):
            continue
        assignment = connection.get("matrix_assignment")
        if not assignment:
            continue
        assignment = str(assignment)
        if assignment in connection_by_assignment:
            raise ProjectGenerationError(
                f'Hardware configuration contains duplicate matrix assignment "{assignment}"',
                code="hardware.duplicate_assignment",
                location=f"hardware.power_supply.hardware_connections[{index}].matrix_assignment",
            )
        connection_by_assignment[assignment] = connection

    metadata_by_assignment: dict[str, Mapping[str, Any]] = {}
    for entry in metadata_entries:
        if not isinstance(entry, Mapping):
            continue
        assignment = entry.get("matrix_assignment")
        if assignment:
            metadata_by_assignment[str(assignment)] = entry

    resources: dict[str, PowerResourceDefinition] = {}
    for assignment, connection in connection_by_assignment.items():
        mode = str(connection.get("mode") or "").lower()
        metadata_entry = metadata_by_assignment.get(assignment, {})
        channel = connection.get("channel") if isinstance(connection.get("channel"), Mapping) else {}

        role = "STRESS" if mode == "switch" else "BIAS"
        parameters = {
            "hardware": True,
            "connection_mode": mode or None,
            "channel_id": channel.get("channel_id"),
            "power_supply_id": channel.get("power_supply_id"),
            "name": metadata_entry.get("name") or channel.get("channel_name"),
            "power_envelopes": metadata_entry.get("power_envelopes") or {},
        }
        resources[assignment] = PowerResourceDefinition(role=role, parameters=parameters)

    return resources


def merge_hardware_power_resources(
    hardware_resources: Mapping[str, PowerResourceDefinition],
    declared_resources: Mapping[str, PowerResourceDefinition],
) -> dict[str, PowerResourceDefinition]:
    unknown = sorted(set(declared_resources) - set(hardware_resources))
    if unknown:
        raise ProjectGenerationError(
            "Declared power resources are not present in the hardware configuration: " + ", ".join(unknown),
            code="hardware.unknown_declared_resource",
            location="power_resources",
            context={"resources": unknown},
        )

    merged = dict(hardware_resources)
    for name, declared in declared_resources.items():
        hardware = hardware_resources[name]
        parameters = dict(declared.parameters)
        parameters.update(hardware.parameters)
        merged[name] = hardware.model_copy(
            update={
                "role": declared.role if declared.role is not None else hardware.role,
                "parameters": parameters,
            }
        )
    return merged


def hardware_power_resource(name: str, resource: PowerResourceDefinition) -> HardwarePowerResource:
    parameters = resource.parameters
    return HardwarePowerResource(
        assignment=name,
        role=(resource.role or "BIAS").upper(),
        connection_mode=str(parameters.get("connection_mode") or "") or None,
        capabilities=PowerSupplyCapabilities.from_mapping(parameters.get("power_envelopes") or {}),
    )


def power_resource_compatibility(
    resource: PowerResourceDefinition,
    bias: Mapping[str, Any],
) -> str | None:
    parameters = resource.parameters
    if not parameters.get("hardware"):
        return None

    connection_mode = str(parameters.get("connection_mode") or "").lower()
    if connection_mode != "bias":
        return f'hardware connection mode is "{connection_mode or "unknown"}", not "bias"'

    try:
        point = OperatingPoint.from_bias(bias)
    except (KeyError, TypeError, ValueError):
        mode = str(bias.get("mode") or "").upper()
        if mode not in {"VOLTAGE", "CURRENT"}:
            return None
        return f"{mode.lower()} bias requires numeric level and compliance values"

    reason = PowerSupplyCapabilities.from_mapping(parameters.get("power_envelopes") or {}).dc_rejection_reason(point)
    return reason.replace("DC maximum", "hardware maximum").replace("DC minimum", "hardware minimum") if reason else None
