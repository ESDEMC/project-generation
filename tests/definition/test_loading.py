import pathlib

import pytest

from project_generation import load_project_definition


from tests.support.paths import EXPLICIT_PROJECT, REALIS

EXAMPLE_DIRECTORY = REALIS


def test_json_generation_definition_loads() -> None:
    definition = load_project_definition(EXPLICIT_PROJECT)
    assert definition.schema_version == "1.0"


def test_yaml_generation_definition_loads() -> None:
    definition = load_project_definition(EXAMPLE_DIRECTORY / "generation.yaml")
    assert definition.schema_version == "1.0"


@pytest.mark.parametrize("suffix", [".yaml", ".yml"])
def test_yaml_extensions_are_supported(tmp_path: pathlib.Path, suffix: str) -> None:
    source = EXAMPLE_DIRECTORY / "generation.yaml"
    definition_path = tmp_path / f"generation{suffix}"
    definition_path.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")

    definition = load_project_definition(definition_path)

    assert definition.schema_version == "1.0"



def test_loaded_definition_retains_absolute_origin() -> None:
    definition_path = EXAMPLE_DIRECTORY / "generation.yaml"

    definition = load_project_definition(definition_path)

    assert definition.definition_path == definition_path.resolve()
    assert definition.definition_directory == definition_path.resolve().parent


def test_relative_json_source_is_resolved_from_generation_file(monkeypatch, tmp_path: pathlib.Path) -> None:
    from project_generation import ProjectGenerationProcessor
    from tests.support.paths import ROOT

    definition_path = ROOT / "examples" / "sources" / "json_pin_source" / "generation.json"
    definition = load_project_definition(definition_path)
    monkeypatch.chdir(tmp_path)

    generated = ProjectGenerationProcessor().process(definition)

    assert generated.name == "External JSON Pin Source"
    assert [pin.designator for pin in generated.pins] == ["1", "2", "3", "4", "5"]


def test_relative_hardware_source_is_resolved_from_generation_file(monkeypatch, tmp_path: pathlib.Path) -> None:
    from project_generation import ProjectGenerationProcessor
    from tests.support.paths import ROOT

    definition_path = ROOT / "examples" / "sources" / "hardware_config" / "generation.yaml"
    definition = load_project_definition(definition_path)
    monkeypatch.chdir(tmp_path)

    generated = ProjectGenerationProcessor().process(definition)

    assignments = {plan.stress_supply.resource for plan in generated.test_plans if plan.stress_supply is not None}
    assert "DC1" in assignments


def test_relative_spreadsheet_source_is_resolved_from_generation_file(monkeypatch, tmp_path: pathlib.Path) -> None:
    from project_generation import ProjectGenerationProcessor
    from tests.support.paths import ROOT

    definition_path = ROOT / "examples" / "sources" / "spreadsheet_pin_source" / "generation.yaml"
    definition = load_project_definition(definition_path)
    monkeypatch.chdir(tmp_path)

    generated = ProjectGenerationProcessor().process(definition)

    assert generated.name == "External Spreadsheet Pin Source"
    assert [pin.designator for pin in generated.pins] == ["1", "2", "3", "4", "5"]


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
