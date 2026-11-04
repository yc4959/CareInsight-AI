import pytest

from careinsight.summary_tool import get_screening_summary


@pytest.fixture(scope="module")
def results():
    return {
        grouping: get_screening_summary(group_by=grouping)
        for grouping in ["overall", "age_group", "gender"]
    }


def test_overall_matches_independently_verified_baseline(results):
    group = results["overall"]["groups"][0]
    assert group["denominator"] == 699
    assert group["numerator"] == 545
    assert group["not_recorded"] == 154
    assert group["coverage"] == pytest.approx(545 / 699)


@pytest.mark.parametrize("grouping", ["age_group", "gender"])
def test_groups_reconcile_to_overall(results, grouping):
    groups = results[grouping]["groups"]
    assert sum(g["denominator"] for g in groups) == 699
    assert sum(g["numerator"] for g in groups) == 545
    assert sum(g["not_recorded"] for g in groups) == 154


def test_age_groups_match_verified_baseline(results):
    actual = {
        g["group"]: (g["numerator"], g["denominator"])
        for g in results["age_group"]["groups"]
    }
    assert actual == {
        "18–39": (185, 250),
        "40–64": (248, 313),
        "65+": (112, 136),
    }


def test_age_comparison(results):
    comparison = results["age_group"]["comparison"]
    assert comparison["lowest_groups"] == ["18–39"]
    assert comparison["highest_groups"] == ["65+"]
    assert comparison["gap_percentage_points"] == pytest.approx(
        (112 / 136 - 185 / 250) * 100
    )


def test_gender_comparison(results):
    result = results["gender"]
    actual = {
        g["group"]: (g["numerator"], g["denominator"])
        for g in result["groups"]
    }
    assert actual == {"F": (301, 388), "M": (244, 311)}
    assert result["missing_group_count"] == 0
    assert result["comparison"]["gap_percentage_points"] == pytest.approx(
        (244 / 311 - 301 / 388) * 100
    )


@pytest.mark.parametrize("year", [2021, "2020", True])
def test_invalid_year_is_rejected(year):
    with pytest.raises(ValueError):
        get_screening_summary(year=year)


def test_unsupported_grouping_is_rejected():
    with pytest.raises(ValueError):
        get_screening_summary(group_by="income")
