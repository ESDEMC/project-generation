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


def test_realis_project_metadata_is_loaded_from_input() -> None:
    from project_generation import ProjectGenerationProcessor

    definition = load_project_definition(EXAMPLE_DIRECTORY / "generation.yaml")
    input_path = next((EXAMPLE_DIRECTORY / "input").glob("L8550_*.json")).resolve()
    token_sources = {
        name: source.model_copy(update={"path": str(input_path)})
        for name, source in definition.sources.items()
        if getattr(source, "path", None) == "{input_file}"
    }
    definition = definition.model_copy(update={"sources": {**definition.sources, **token_sources}})

    generated = ProjectGenerationProcessor().process(definition, base_directory=EXAMPLE_DIRECTORY)

    assert generated.name == "Q25FMA14_FMA103"
    assert generated.metadata["test_id"] == 3263975
    assert generated.metadata["lab_tracking_number"] == "VQ254216.13-FMA103U"
    assert generated.metadata["sales_code"] == "BTS80320-SSPL-4ES"
