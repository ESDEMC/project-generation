import pathlib
import uuid
from typing import Any, Mapping

from project_generation.definition.models import DutDefinition, NameTemplateDefinition, ProjectGenerationDefinition, SourceDefinition
from project_generation.diagnostics import ProjectGenerationError
from project_generation.generation.hardware import load_hardware_power_resources, merge_hardware_power_resources
from project_generation.generation.helpers import _OMIT, merge_value_tree, render_value_template, resolve_value_tree
from project_generation.generation.models import GeneratedPin
from project_generation.generation.sources import load_source_records
from project_generation.version import get_package_version

_PACKAGE_VERSION = get_package_version()
_PROJECT_GENERATION_NAMESPACE = uuid.UUID("b5cc252e-8608-4e8c-a03f-8ce6e5f55b43")


class ProjectInputGenerator:
    def __init__(self, definition: ProjectGenerationDefinition, base_directory: pathlib.Path):
        self.definition = definition
        self.base_directory = base_directory

    def _resolve_dut_name(self, definition: ProjectGenerationDefinition) -> str | None:
        if definition.dut is None:
            return None

        name_definition = definition.dut.name
        context = {
            "project": {
                "name": definition.project.name,
                "metadata": dict(definition.project.metadata),
            }
        }
        if isinstance(name_definition, str):
            name = name_definition
        elif isinstance(name_definition, NameTemplateDefinition):
            name = render_value_template(
                name_definition.model_dump(by_alias=True, exclude_none=True),
                context,
                owner="DUT name",
                mappings=definition.mappings,
                formatters=definition.formatters,
            )
        else:
            name = resolve_value_tree(name_definition, context, definition=definition)

        if name is _OMIT or name is None or not str(name).strip():
            raise ProjectGenerationError(
                "DUT name did not resolve to a non-empty value",
                code="dut.missing_name",
                location="dut.name",
            )
        return str(name)

    @staticmethod
    def _load_power_resources(
        definition: ProjectGenerationDefinition,
        base_directory: pathlib.Path,
    ) -> dict[str, Any]:
        if definition.hardware is None:
            return dict(definition.power_resources)

        source_path = pathlib.Path(definition.hardware.source)
        if not source_path.is_absolute():
            source_path = base_directory / source_path
        hardware_resources = load_hardware_power_resources(source_path)
        return merge_hardware_power_resources(hardware_resources, definition.power_resources)

    def _load_project_metadata(
        self,
        definition: ProjectGenerationDefinition,
        base_directory: pathlib.Path,
    ) -> tuple[str, dict[str, Any]]:
        project_values: dict[str, Any] = {
            "name": definition.project.name,
            "metadata": dict(definition.project.metadata),
        }
        project_values["metadata"]["project_generator_version"] = _PACKAGE_VERSION
        if definition.project.source is not None:
            try:
                source = definition.sources[definition.project.source]
            except KeyError as error:
                raise ProjectGenerationError(
                    f'Unknown project source "{definition.project.source}"',
                    code="project.unknown_source",
                    location="project.source",
                ) from error
            records = load_source_records(
                source,
                base_directory=base_directory,
                mappings=definition.mappings,
                formatters=definition.formatters,
            )
            if len(records) != 1:
                raise ProjectGenerationError(
                    f'Project source "{definition.project.source}" must resolve to exactly one record; received {len(records)}',
                    code="project.invalid_source_count",
                    location="project.source",
                )
            merge_value_tree(project_values, records[0])

        name = project_values.get("name")
        if name is None or not str(name).strip():
            raise ProjectGenerationError(
                "Project metadata does not define a name",
                code="project.missing_name",
                location="project.name",
            )
        metadata = project_values.get("metadata", {})
        if not isinstance(metadata, Mapping):
            raise ProjectGenerationError(
                "Project metadata must resolve to an object",
                code="project.invalid_metadata",
                location="project.metadata",
            )
        return str(name), dict(metadata)

    def _load_pins(self, definition: ProjectGenerationDefinition, base_directory: pathlib.Path) -> list[GeneratedPin]:
        if definition.dut is None:
            return []
        source = self._resolve_pin_source(definition, definition.dut)
        records = load_source_records(
            source,
            base_directory=base_directory,
            mappings=definition.mappings,
            formatters=definition.formatters,
        )
        namespace = uuid.uuid5(_PROJECT_GENERATION_NAMESPACE, f"{definition.project.name}:{definition.dut.name}")
        pins: list[GeneratedPin] = []
        designators: set[str] = set()
        for index, record in enumerate(records):
            designator = record.get("designator")
            name = record.get("name")
            if designator is None:
                raise ProjectGenerationError(
                    f"Pin record {index} does not define designator",
                    code="pin.missing_designator",
                    location=f"dut.pins.records[{index}]",
                    owner=definition.dut.name,
                )
            if name is None:
                raise ProjectGenerationError(
                    f"Pin record {index} does not define name",
                    code="pin.missing_name",
                    location=f"dut.pins.records[{index}]",
                    owner=definition.dut.name,
                )
            designator = str(designator)
            if designator in designators:
                raise ProjectGenerationError(
                    f'Duplicate pin designator "{designator}"',
                    code="pin.duplicate_designator",
                    location=f"dut.pins.records[{index}].designator",
                    owner=definition.dut.name,
                    context={"designator": designator},
                )
            designators.add(designator)
            parameters = record.get("parameters", {})
            if not isinstance(parameters, Mapping):
                raise ProjectGenerationError(f'Pin "{designator}" parameters must be an object')
            pins.append(
                GeneratedPin(
                    id=uuid.uuid5(namespace, designator),
                    designator=designator,
                    name=str(name),
                    parameters=dict(parameters),
                )
            )
        return pins

    @staticmethod
    def _resolve_pin_source(definition: ProjectGenerationDefinition, dut: DutDefinition) -> SourceDefinition:
        source = dut.pins.source
        if isinstance(source, str):
            try:
                return definition.sources[source]
            except KeyError as error:
                raise ProjectGenerationError(
                f'Unknown pin source "{source}"',
                code="source.unknown",
                location="dut.pins.source",
                owner=dut.name,
                context={"source": source},
            ) from error
        return source

    def generate(self) -> tuple[ProjectGenerationDefinition, str, dict[str, Any], list[GeneratedPin]]:
        definition = self.definition
        base_directory = self.base_directory

        power_resources = self._load_power_resources(definition, base_directory)
        definition = definition.model_copy(update={"power_resources": power_resources})

        project_name, project_metadata = self._load_project_metadata(definition, base_directory)
        effective_project = definition.project.model_copy(
            update={"name": project_name, "metadata": project_metadata}
        )
        definition = definition.model_copy(update={"project": effective_project})

        dut_name = self._resolve_dut_name(definition)
        if definition.dut is not None:
            definition = definition.model_copy(
                update={"dut": definition.dut.model_copy(update={"name": dut_name})}
            )

        pins = self._load_pins(definition, base_directory)
        return definition, project_name, project_metadata, pins

