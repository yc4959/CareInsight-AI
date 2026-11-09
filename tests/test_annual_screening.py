"""Cross-year screening counts must retain year-specific cohort rules."""

import json

import pytest

from careinsight import open_analysis
from careinsight.read_only_sql import run_aggregate_sql
from careinsight.summary_tool import get_screening_summary
from careinsight.verified_screening_sql import build_verified_screening_sql


@pytest.mark.parametrize("year", [2019, 2020])
@pytest.mark.parametrize("metric", ["depression", "substance_use"])
@pytest.mark.parametrize("group_by", ["overall", "age_group", "gender"])
def test_annual_sql_matches_independent_pandas(year, metric, group_by):
    query = run_aggregate_sql(build_verified_screening_sql(
        year=year, metric=metric, group_by=group_by
    ))
    actual = {row["group_name"]: (row["denominator"], row["numerator"])
              for row in query["rows"]}
    reference = get_screening_summary(year=year, metric=metric, group_by=group_by)
    expected = {row["group"]: (row["denominator"], row["numerator"])
                for row in reference["groups"]}
    assert actual == expected


def test_trend_runs_both_years_and_checks_each(monkeypatch):
    for key in ("DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL", "DEEPSEEK_MODEL"):
        monkeypatch.setenv(key, "offline-test")
    arguments = {"metric": "substance_use", "start_year": 2019,
                 "end_year": 2020, "plan": "2019 adults born before 2019-01-01."}
    monkeypatch.setattr(open_analysis, "call_model", lambda messages, tools: {
        "tool_calls": [{"id": "offline", "function": {
            "name": "run_verified_screening_trend",
            "arguments": json.dumps(arguments),
        }}]
    })
    result = open_analysis.analyze(
        "How did substance use screening record coverage change between 2019 and 2020?"
    )
    assert result["status"] == "validated"
    assert result["metric_reference"]["trend"] is True
    assert "2001-01-01" in result["plan"]
    assert "2002-01-01" in result["plan"]
    assert "born before 2019-01-01" not in result["plan"]
    assert [(row["group_name"], row["denominator"], row["numerator"])
            for row in result["query"]["rows"]] == [
                ("2019", 674, 219), ("2020", 699, 230),
            ]


def test_2019_single_year_uses_2019_cohort(monkeypatch):
    for key in ("DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL", "DEEPSEEK_MODEL"):
        monkeypatch.setenv(key, "offline-test")
    arguments = {"metric": "depression", "group_by": "overall", "year": 2019,
                 "plan": "Count eligible adults with a 2019 depression screening record."}
    monkeypatch.setattr(open_analysis, "call_model", lambda messages, tools: {
        "tool_calls": [{"id": "offline", "function": {
            "name": "run_verified_screening", "arguments": json.dumps(arguments),
        }}]
    })
    result = open_analysis.analyze(
        "How many adults had a depression screening record in 2019?"
    )
    assert result["status"] == "validated"
    assert result["query"]["rows"] == [{
        "group_name": "All eligible adults", "denominator": 674, "numerator": 510,
    }]


def test_incomplete_year_not_marked_as_reviewed():
    with pytest.raises(ValueError, match="2019 and 2020"):
        get_screening_summary(year=2021)
    with pytest.raises(ValueError, match="2019 and 2020"):
        build_verified_screening_sql(year=2021, metric="depression", group_by="overall")
