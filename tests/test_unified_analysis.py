"""Offline regression checks for both paths through the unified agent."""

import json

from careinsight import open_analysis
from careinsight.read_only_sql import run_aggregate_sql
from careinsight.summary_tool import get_screening_summary
from careinsight.verified_screening_sql import build_verified_screening_sql


def _fake_reply(tool, arguments):
    return {"tool_calls": [{"id": "offline-test", "function": {
        "name": tool, "arguments": json.dumps(arguments),
    }}]}


def test_every_reviewed_metric_and_group_matches_independent_reference():
    for metric in ("depression", "substance_use"):
        for group_by in ("overall", "age_group", "gender"):
            sql = build_verified_screening_sql(
                metric=metric, group_by=group_by, year=2020
            )
            actual = {row["group_name"]: (row["denominator"], row["numerator"])
                      for row in run_aggregate_sql(sql)["rows"]}
            reference = get_screening_summary(metric=metric, group_by=group_by)
            expected = {row["group"]: (row["denominator"], row["numerator"])
                        for row in reference["groups"]}
            assert actual == expected


def test_unified_agent_publishes_reviewed_result(monkeypatch):
    for name in ("DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL", "DEEPSEEK_MODEL"):
        monkeypatch.setenv(name, "offline-test-only")
    arguments = {"metric": "substance_use", "group_by": "gender", "year": 2020,
                 "plan": "Compare adult screening record coverage by GENDER."}
    monkeypatch.setattr(open_analysis, "call_model", lambda messages, tools:
                        _fake_reply("run_verified_screening", arguments))
    result = open_analysis.analyze(
        "Compare substance use screening records between men and women in 2020."
    )
    assert result["status"] == "validated"
    assert result["validation_level"] == "independent_metric_reference"
    assert result["attempts"][0]["status"] == "validated"
    assert {row["group_name"]: (row["denominator"], row["numerator"])
            for row in result["query"]["rows"]} == {
                "F": (388, 113), "M": (311, 117),
            }
    assert all("not independently verified" not in check
               for check in result["checks"])


def test_unified_agent_keeps_other_questions_exploratory(monkeypatch):
    for name in ("DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL", "DEEPSEEK_MODEL"):
        monkeypatch.setenv(name, "offline-test-only")
    arguments = {"plan": "Count 2020 procedure records by description.",
                 "table": "procedures", "year": 2020,
                 "group_by": "DESCRIPTION", "aggregation": "row_count",
                 "filter_column": "none", "filter_value": "", "limit": 10}
    monkeypatch.setattr(open_analysis, "call_model", lambda messages, tools:
                        _fake_reply("run_pandas_aggregate", arguments))
    result = open_analysis.analyze(
        "Which procedure descriptions appeared most often in 2020? Show the top 10."
    )
    assert result["status"] == "exploratory"
    assert result["tool"] == "run_pandas_aggregate"
    assert result["cross_check"]["passed"] is True
    assert result["query"]["rows"][0]["value"] == 812
