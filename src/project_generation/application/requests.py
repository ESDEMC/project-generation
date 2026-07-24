from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, kw_only=True)
class GenerateProjectRequest:
    project_name: str
    definition_path: Path
    input_path: Path
    output_directory: Path

    def validate(self) -> None:
        if not self.project_name:
            raise ValueError("Project name is required")
        if not self.definition_path.is_file():
            raise FileNotFoundError(f"Generation definition does not exist: {self.definition_path}")
        if self.definition_path.suffix.lower() not in {".json", ".yaml", ".yml"}:
            raise ValueError("Generation definition must be a JSON or YAML file")
        if not self.input_path.is_file():
            raise FileNotFoundError(f"Generation input does not exist: {self.input_path}")
        if self.output_directory.exists() and not self.output_directory.is_dir():
            raise NotADirectoryError(f"Output path is not a directory: {self.output_directory}")
        self.output_directory.mkdir(parents=True, exist_ok=True)
