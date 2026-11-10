"""A completed result can supply context for a fresh, reviewed analysis."""

import json
from pathlib import Path

from careinsight import open_analysis
from careinsight.followup_context import context_from_result
from streamlit.testing.v1 import AppTest


def _reply(args):
    return {"tool_calls": [{"id": "offline-followup", "function": {
        "name": "run_verified_screening", "arguments": json.dumps(args),
    }}]}


def test_followup_changes_group_without_losing_measure_or_year(monkeypatch):
    for name in ("DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL", "DEEPSEEK_MODEL"):
        monkeypatch.setenv(name, "offline-test-only")
    args = {"metric": "substance_use", "group_by": "gender", "year": 2020,
            "plan": "Compare substance use screening records by gender."}
    monkeypatch.setattr(open_analysis, "call_model", lambda *_: _reply(args))
    first = open_analysis.analyze(
        "Compare substance use screening records between men and women in 2020."
    )
    assert first["status"] == "validated"
    context = context_from_result(first)
    assert "substance use" in context[0]["content"]
    assert "2020" in context[0]["content"]

    args = {**args, "group_by": "age_group", "plan": "Break down by age group."}
    second = open_analysis.analyze("What about by age group?", history=context)
    assert second["status"] == "validated"
    assert [row["group_name"] for row in second["query"]["rows"]] == [
        "18–39", "40–64", "65+"
    ]
    assert second["attempts"][0]["status"] == "validated"


def test_followup_can_change_measure_then_keep_new_measure(monkeypatch):
    for name in ("DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL", "DEEPSEEK_MODEL"):
        monkeypatch.setenv(name, "offline-test-only")
    args = {"metric": "depression", "group_by": "overall", "year": 2019,
            "plan": "Count depression screening records in 2019."}
    monkeypatch.setattr(open_analysis, "call_model", lambda *_: _reply(args))
    first = open_analysis.analyze("How many adults had a depression screening record in 2019?")
    assert first["status"] == "validated"

    args = {**args, "metric": "substance_use",
            "plan": "Count substance use screening records in 2019."}
    second = open_analysis.analyze("What about substance use?",
                                   history=context_from_result(first))
    assert second["status"] == "validated"
    assert second["query"]["rows"][0]["numerator"] == 219
    assert "substance use" in context_from_result(second)[0]["content"]


def test_streamlit_followup_runs_a_new_analysis(monkeypatch):
    for name in ("DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL", "DEEPSEEK_MODEL"):
        monkeypatch.setenv(name, "offline-test-only")
    calls = []

    def fake_model(messages, tools):
        question = messages[-1]["content"]
        calls.append(question)
        group = "age_group" if question == "What about by age group?" else "gender"
        return _reply({"metric": "substance_use", "group_by": group,
                       "year": 2020, "plan": f"Compare screening by {group}."})

    monkeypatch.setattr(open_analysis, "call_model", fake_model)
    app_path = Path(__file__).resolve().parents[1] / "app.py"
    app = AppTest.from_file(app_path, default_timeout=30).run()
    next(button for button in app.button if button.label == "Analyze").click().run()
    assert app.session_state["explore_result"]["status"] == "validated"
    next(button for button in app.button
         if button.label == "Ask a follow-up about this result").click().run()
    next(field for field in app.text_input
         if field.label == "Follow-up question").set_value("What about by age group?")
    next(button for button in app.button
         if button.label == "Analyze follow-up").click().run()
    assert not app.exception
    result = app.session_state["explore_result"]
    assert result["status"] == "validated"
    assert [row["group_name"] for row in result["query"]["rows"]] == [
        "18–39", "40–64", "65+"
    ]
    assert calls == [
        "Compare adult substance use screening record coverage by GENDER in 2020.",
        "What about by age group?",
    ]
