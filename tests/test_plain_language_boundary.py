"""Ambiguous everyday wording must be clarified before tool selection."""

import pytest

from careinsight import open_analysis


@pytest.mark.parametrize("question", [
    "How many adults were checked for depression in 2020?",
    "How many people got checked for depression last year?",
    "Were more men or women checked for depression?",
    "How many people were checked for substance use in 2019?",
    "What share of adults got checked for drug abuse in 2020?",
])
def test_ambiguous_check_wording_asks_before_model_or_query(monkeypatch, question):
    monkeypatch.setattr(open_analysis, "_latest_observed_year", lambda: 2021)
    monkeypatch.setattr(open_analysis, "call_model", lambda *_: pytest.fail(
        "The model should not be called before clarification."
    ))
    result = open_analysis.analyze(question)
    assert result["status"] == "no_analysis"
    assert result["attempts"] == []
    assert "recorded screening" in result["message"]
    assert "diagnosed" in result["message"]


@pytest.mark.parametrize("question", [
    "How many adults had a recorded depression screening in 2020?",
    "How many people were checked for depression screening records in 2020?",
    "How many adults had a depression diagnosis in 2020?",
    "What procedures were recorded most often in 2020?",
])
def test_specific_wording_does_not_trigger_checked_for_clarification(question):
    assert open_analysis._request_boundary(question) is None
