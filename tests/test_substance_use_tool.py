import pytest

from careinsight.summary_tool import get_screening_summary


def test_substance_use_overall_matches_independent_audit():
    result = get_screening_summary(metric="substance_use")
    group = result["groups"][0]
    assert result["metric_id"] == "adult_substance_use_screening_record_coverage_v1"
    assert (group["numerator"], group["denominator"]) == (230, 699)
    assert group["not_recorded"] == 469
    assert group["coverage"] == pytest.approx(230 / 699)


@pytest.mark.parametrize(
    ("grouping", "expected"),
    [
        ("age_group", {"18–39": (72, 250), "40–64": (114, 313), "65+": (44, 136)}),
        ("gender", {"F": (113, 388), "M": (117, 311)}),
    ],
)
def test_substance_use_groups_match_independent_audit(grouping, expected):
    result = get_screening_summary(metric="substance_use", group_by=grouping)
    actual = {
        group["group"]: (group["numerator"], group["denominator"])
        for group in result["groups"]
    }
    assert actual == expected
    assert sum(n for n, _ in actual.values()) == 230
    assert sum(d for _, d in actual.values()) == 699


def test_unknown_metric_is_rejected():
    with pytest.raises(ValueError):
        get_screening_summary(metric="diagnosis")
