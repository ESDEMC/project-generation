from tests.support.paths import GROUPED_BY_TYPE_AND_VOLTAGE
from project_generation import GroupRecord, load_project_definition, partition_groups


def test_group_by_partition() -> None:
    definition = load_project_definition(GROUPED_BY_TYPE_AND_VOLTAGE)
    rule = definition.test_plan_generation.rules[0]
    groups = [
        GroupRecord(name="IN_A", group_type="INPUT", parameters={"v_max": 5.5}),
        GroupRecord(name="IN_B", group_type="INPUT", parameters={"v_max": 5.5}),
        GroupRecord(name="IN_C", group_type="INPUT", parameters={"v_max": 3.3}),
        GroupRecord(name="OUT_A", group_type="OUTPUT", parameters={"v_max": 5.5}),
    ]

    partitions = partition_groups(rule, groups)
    assert sorted(len(partition.groups) for partition in partitions) == [1, 1, 2]
