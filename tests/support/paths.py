from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = ROOT / "examples"
FIXTURES = ROOT / "tests" / "fixtures"

EXPLICIT_PROJECT = EXAMPLES / "basics" / "explicit_project" / "generation.json"
JSON_PIN_SOURCE = EXAMPLES / "sources" / "json_pin_source" / "generation.json"
GROUP_GENERATION = EXAMPLES / "customizing_generation" / "group_generation" / "generation.json"
DEVICE_STATES_AND_POWER_ALLOCATION = (
    EXAMPLES / "customizing_generation" / "device_states_and_power_allocation" / "generation.json"
)
TEST_PLAN_DIMENSIONS = EXAMPLES / "customizing_generation" / "test_plan_dimensions" / "generation.json"
STRESS_SERIES_AND_OVERRIDES = EXAMPLES / "customizing_generation" / "stress_series_and_overrides" / "generation.json"
GROUPED_BY_TYPE_AND_VOLTAGE = FIXTURES / "partitioning" / "grouped_by_type_and_voltage.json"
REALIS = EXAMPLES / "real_world" / "realis"
