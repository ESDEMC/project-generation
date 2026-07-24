import re
from pathlib import Path

from project_generation.models import ProjectGenerationDefinition
from project_generation.project_processor import ProjectGenerationProcessor

from .ports import ProjectWriter, ProjectGenerationAdapter
from .requests import GenerateProjectRequest


def file_name(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    return normalized.strip("._") or "project"


class GenerateProject:
    def __init__(self, *, adapter: ProjectGenerationAdapter, writer: ProjectWriter) -> None:
        self._adapter = adapter
        self._writer = writer

    def execute(self, request: GenerateProjectRequest) -> Path:
        request.validate()
        definition = ProjectGenerationDefinition.load(request.definition_path)
        definition = self._set_input_file(definition, request.input_path)
        generated_project = ProjectGenerationProcessor().process(
            definition,
            base_directory=request.definition_path.parent,
        )
        artifacts = self._adapter.adapt(generated_project)
        return self._writer.write(artifacts, request=request)

    @staticmethod
    def _set_input_file(
        definition: ProjectGenerationDefinition,
        input_path: Path,
    ) -> ProjectGenerationDefinition:
        sources = {}
        for name, source in definition.sources.items():
            source_path = getattr(source, "path", None)
            if source_path is None or "{input_file}" not in source_path:
                sources[name] = source
                continue
            sources[name] = source.model_copy(
                update={"path": source_path.replace("{input_file}", str(input_path))}
            )
        return definition.model_copy(update={"sources": sources})
