import pytest

from project_generation import (
    ProjectGenerationDefinition,
    ProjectGenerationError,
    ProjectGenerationProcessor,
)


def test_unknown_pin_source_has_structured_diagnostic() -> None:
    definition = ProjectGenerationDefinition.model_validate(
        {
            "schema_version": "1.0.0",
            "project": {"name": "diagnostics"},
            "dut": {"name": "DUT", "pins": {"source": "missing"}},
            "sources": {},
        }
    )

    with pytest.raises(ProjectGenerationError) as captured:
        ProjectGenerationProcessor().process(definition)

    error = captured.value
    assert error.code == "source.unknown"
    assert error.location == "dut.pins.source"
    assert error.owner == "DUT"
    assert error.context == {"owner": "DUT", "source": "missing"}
    assert error.diagnostic.message == 'Unknown pin source "missing"'
    assert error.format_diagnostic() == 'ERROR source.unknown at dut.pins.source: Unknown pin source "missing"'


def test_explicit_group_error_identifies_definition_owner() -> None:
    definition = ProjectGenerationDefinition.model_validate(
        {
            "schema_version": "1.0.0",
            "project": {"name": "diagnostics"},
            "dut": {
                "name": "DUT",
                "pins": {
                    "source": {
                        "type": "inline",
                        "records": [{"designator": "1", "name": "A"}],
                    }
                },
            },
            "groups": {
                "explicit": [
                    {
                        "name": "SUPPLY",
                        "group_type": "POWER",
                        "pins": ["2"],
                    }
                ]
            },
        }
    )

    with pytest.raises(ProjectGenerationError) as captured:
        ProjectGenerationProcessor().process(definition)

    error = captured.value
    assert error.code == "group.unknown_pins"
    assert error.location == "groups.explicit[SUPPLY].pins"
    assert error.owner == "SUPPLY"
    assert error.context["missing_designators"] == ["2"]


def test_legacy_exception_message_is_preserved() -> None:
    error = ProjectGenerationError(
        "plain failure",
        code="example.failure",
        location="example.path",
        owner="example",
    )

    assert str(error) == "plain failure"
    assert isinstance(error, ValueError)


def test_power_resolution_error_exposes_ui_friendly_context() -> None:
    from project_generation import (
        PowerResourceCandidateDiagnostic,
        PowerResourceResolutionError,
        PowerResourceResolutionIssue,
    )

    error = PowerResourceResolutionError(
        (
            PowerResourceResolutionIssue(
                state_name="active",
                group_name="VDD",
                bias={"mode": "VOLTAGE", "level": 5.0, "compliance_limit": 2.0},
                candidates=(
                    PowerResourceCandidateDiagnostic(
                        resource="DC2",
                        accepted=False,
                        reason="current requirement exceeds the DC envelope",
                    ),
                ),
            ),
        )
    )

    assert error.context["issues"][0]["group_name"] == "VDD"
    assert error.context["issues"][0]["candidates"][0] == {
        "resource": "DC2",
        "accepted": False,
        "reason": "current requirement exceeds the DC envelope",
    }
    assert "compliance_limit: 2.0" in error.format_user_report()
    assert "DC2: rejected - current requirement exceeds the DC envelope" in error.format_user_report()
