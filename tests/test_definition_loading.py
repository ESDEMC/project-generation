import pathlib

import pytest

from project_generation import load_project_definition


EXAMPLE_DIRECTORY = pathlib.Path(__file__).parents[1] / "examples" / "realis"


def test_json_and_yaml_generation_definitions_are_equivalent() -> None:
    json_definition = load_project_definition(EXAMPLE_DIRECTORY / "generation.json")
    yaml_definition = load_project_definition(EXAMPLE_DIRECTORY / "generation.yaml")

    assert yaml_definition.model_dump(mode="json") == json_definition.model_dump(mode="json")


@pytest.mark.parametrize("suffix", [".yaml", ".yml"])
def test_yaml_extensions_are_supported(tmp_path: pathlib.Path, suffix: str) -> None:
    source = EXAMPLE_DIRECTORY / "generation.yaml"
    definition_path = tmp_path / f"generation{suffix}"
    definition_path.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")

    definition = load_project_definition(definition_path)

    assert definition.schema_version == "1.0"


def test_unknown_definition_extension_is_rejected(tmp_path: pathlib.Path) -> None:
    definition_path = tmp_path / "generation.toml"
    definition_path.write_text("schema_version = '1.0'\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Unsupported generation definition format"):
        load_project_definition(definition_path)
