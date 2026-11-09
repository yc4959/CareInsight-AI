import json

import pytest

from careinsight import chat_ui


def tool_reply(metric, group_by="gender"):
    return {
        "tool_calls": [{
            "id": "test-call",
            "function": {
                "name": "get_screening_summary",
                "arguments": json.dumps({
                    "year": 2020,
                    "group_by": group_by,
                    "metric": metric,
                }),
            },
        }],
    }


def make_state(question, answers=None):
    return {
        "question": question,
        "messages": [],
        "clarification_history": [
            {"question": "Which screening?", "answer": answer}
            for answer in (answers or [])
        ],
        "pending": None,
        "clarifications": len(answers or []),
        "notice": None,
    }


def test_both_answer_produces_two_separate_reports(monkeypatch):
    monkeypatch.setattr(
        chat_ui, "call_model",
        lambda messages, tools: tool_reply("depression"),
    )
    state = make_state(
        "Compare screening records between men and women in 2020.",
        ["Both"],
    )

    chat_ui.process_turn(state)

    assert len(state["evidence"]["result"]) == 2
    assert "301 of 388" in state["report"]
    assert "113 of 388" in state["report"]
    assert "Adult depression screening records" in state["report"]
    assert "Adult substance use screening records" in state["report"]


def test_single_metric_stays_single(monkeypatch):
    monkeypatch.setattr(
        chat_ui, "call_model",
        lambda messages, tools: tool_reply("substance_use", "overall"),
    )
    state = make_state(
        "How many adults had a substance use screening record in 2020?"
    )

    chat_ui.process_turn(state)

    assert isinstance(state["evidence"]["result"], dict)
    assert "230 of 699" in state["report"]
    assert "Adult depression screening records" not in state["report"]


def test_unsupported_metric_is_rejected(monkeypatch):
    monkeypatch.setattr(
        chat_ui, "call_model",
        lambda messages, tools: tool_reply("diagnosis"),
    )
    state = make_state("Compare diagnosis records by gender in 2020.")

    with pytest.raises(ValueError, match="Unsupported metric"):
        chat_ui.process_turn(state)
