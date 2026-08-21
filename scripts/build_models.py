import argparse
import importlib.util
import os
import py_compile
import subprocess
import sys
import tempfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCHEMA_PATH = PROJECT_ROOT / "project-generation.schema.json"
REQUIRED_MODEL_CLASSES = {
    "AllocationDefinition",
    "CsvSource",
    "DimensionDefinition",
    "DutDefinition",
    "ExcelSource",
    "ExplicitGroupDefinition",
    "ExplicitTestPlanDefinition",
    "FormatterDefinition",
    "GroupByFieldDefinition",
    "GroupGenerationRule",
    "HardwareDefinition",
    "InlineSource",
    "JsonSource",
    "NameFieldDefinition",
    "ProjectGenerationDefinition",
    "SourceFieldMapping",
    "TestPlanRuleDefinition",
}


def package_directory() -> Path:
    src_package = PROJECT_ROOT / "src" / "project_generation"
    if src_package.is_dir():
        return src_package
    package = PROJECT_ROOT / "project_generation"
    if package.is_dir():
        return package
    raise FileNotFoundError("Could not find src/project_generation or project_generation")


def default_output_path() -> Path:
    return package_directory() / "definition" / "generated_models.py"


def build_models(schema_path: Path, output_path: Path) -> None:
    if not schema_path.is_file():
        raise FileNotFoundError(f"Schema file not found: {schema_path}")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="project-generation-models-") as temporary_directory:
        temporary_output = Path(temporary_directory) / "generated_models.py"
        generate_models(schema_path, temporary_output)
        py_compile.compile(str(temporary_output), doraise=True)
        verify_required_classes(temporary_output)

        previous_contents = output_path.read_text(encoding="utf-8") if output_path.exists() else None
        output_path.write_text(temporary_output.read_text(encoding="utf-8"), encoding="utf-8")
        try:
            verify_package_imports()
        except Exception:
            if previous_contents is None:
                output_path.unlink(missing_ok=True)
            else:
                output_path.write_text(previous_contents, encoding="utf-8")
            raise


def generate_models(schema_path: Path, output_path: Path) -> None:
    if importlib.util.find_spec("datamodel_code_generator") is None:
        raise RuntimeError(
            "datamodel-code-generator is required to rebuild definition models. "
            "Install it in the development environment first."
        )

    command = [
        sys.executable,
        "-m",
        "datamodel_code_generator",
        "--input",
        str(schema_path),
        "--input-file-type",
        "jsonschema",
        "--output",
        str(output_path),
        "--output-model-type",
        "pydantic_v2.BaseModel",
        "--target-python-version",
        "3.11",
        "--use-standard-collections",
        "--use-union-operator",
        "--disable-timestamp",
        "--formatters",
        "builtin",
    ]
    subprocess.run(command, check=True)


def verify_required_classes(path: Path) -> None:
    import ast

    module = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    class_names = {node.name for node in module.body if isinstance(node, ast.ClassDef)}
    missing = sorted(REQUIRED_MODEL_CLASSES - class_names)
    if missing:
        raise RuntimeError(f"Generated model file is missing required classes: {', '.join(missing)}")


def verify_package_imports() -> None:
    package = package_directory()
    python_path = package.parent
    environment = dict(os.environ)
    existing_python_path = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = (
        str(python_path) if not existing_python_path else os.pathsep.join((str(python_path), existing_python_path))
    )

    smoke_code = """
from project_generation.definition.models import ProjectGenerationDefinition
from project_generation.generation.processor import ProjectGenerationProcessor

payload = {
    "schema_version": "1.0",
    "project": {"name": "model-build-smoke-test"},
    "mappings": {"prefix": {"POWER": "Su", "INPUT": "In"}},
    "formatters": {"voltage": {"type": "decimal_token", "separator": "V", "decimal_places": 1}},
    "dut": {
        "name": "DUT",
        "pins": {
            "source": {
                "type": "inline",
                "records": [
                    {"designator": "1", "name": "VDD", "parameters": {"pin_type": "POWER", "v_max": "5.0"}},
                    {"designator": "2", "name": "IN", "parameters": {"pin_type": "INPUT", "v_max": "3.3"}},
                ],
            }
        },
    },
    "groups": {
        "generation": [
            {
                "id": "groups",
                "group_by": ["parameters.pin_type", "parameters.v_max"],
                "set": {
                    "group_type": {"from": "partition.parameters.pin_type"},
                    "parameters.v_max": {"from": "partition.parameters.v_max", "cast": "float"},
                    "parameters.compliance_limit": [
                        {"when": {"partition.parameters.pin_type": "POWER"}, "value": 0.2},
                        {
                            "when": {"partition.parameters.pin_type": {"in": ["INPUT", "IO", "OUTPUT"]}},
                            "value": 0.12,
                        },
                    ],
                },
                "name": {
                    "template": "{prefix}{voltage}",
                    "fields": {
                        "prefix": {"source": "partition.parameters.pin_type", "mapping": "prefix"},
                        "voltage": {
                            "source": "partition.parameters.v_max",
                            "formatter": "voltage",
                            "when": {"partition.parameters.pin_type": {"in": ["INPUT", "IO", "OUTPUT"]}},
                        },
                    },
                },
            }
        ]
    },
}

definition = ProjectGenerationDefinition.model_validate(payload)
project = ProjectGenerationProcessor().process(definition)
actual = {group.group_type: (group.name, dict(group.parameters)) for group in project.groups}
assert actual["POWER"] == ("Su", {"v_max": 5.0, "compliance_limit": 0.2})
assert actual["INPUT"] == ("In3V3", {"v_max": 3.3, "compliance_limit": 0.12})
"""
    subprocess.run([sys.executable, "-c", smoke_code], check=True, cwd=PROJECT_ROOT, env=environment)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate Pydantic definition models from project-generation.schema.json.")
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA_PATH)
    parser.add_argument("--output", type=Path, default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_path = args.output.resolve() if args.output is not None else default_output_path().resolve()
    try:
        build_models(args.schema.resolve(), output_path)
    except (FileNotFoundError, py_compile.PyCompileError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"Failed to build models: {error}", file=sys.stderr)
        return 1
    print(f"Generated models: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
