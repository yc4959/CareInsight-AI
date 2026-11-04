import json
import os
from datetime import datetime, timezone
from pathlib import Path

from careinsight.agent import SYSTEM, TOOLS
from careinsight.agent_demo import call_model

ROOT = Path(__file__).resolve().parents[1]


def evaluate_case(case):
    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": case["question"]},
    ]
    reply = call_model(messages, TOOLS)
    calls = reply.get("tool_calls") or []

    result = {
        **case,
        "status": "fail",
        "observed_tool": None,
        "observed_arguments": None,
        "response_text": reply.get("content"),
    }

    if not calls:
        result["status"] = "manual_review"
        result["reason"] = (
            "No tool call. Review the text for clarification, refusal, "
            "or unsupported factual claims."
        )
        return result

    if len(calls) != 1:
        result["reason"] = "Expected at most one tool call."
        return result

    function = calls[0]["function"]
    name = function["name"]
    args = json.loads(function["arguments"])
    result["observed_tool"] = name
    result["observed_arguments"] = args

    expected = case["expected_behavior"]
    if expected == "analyze":
        correct = (
            name == "get_screening_summary"
            and isinstance(args, dict)
            and set(args) == {"year", "group_by"}
            and type(args["year"]) is int
            and args["year"] == 2020
            and args["group_by"] == case["expected_group_by"]
        )
        result["status"] = "routing_pass" if correct else "fail"
        result["reason"] = "Checked tool name and exact analysis parameters."
    elif expected == "clarify":
        correct = (
            name == "ask_clarification"
            and isinstance(args, dict)
            and set(args) == {"question"}
            and isinstance(args["question"], str)
            and bool(args["question"].strip())
        )
        result["status"] = "clarification_review" if correct else "fail"
        result["reason"] = (
            "Review whether the clarification resolves the ambiguity."
            if correct else "Expected a clarification tool call."
        )
    else:
        result["reason"] = (
            "Expected a refusal without executing a substitute analysis. "
            "Review any clarification call separately."
        )

    return result


def main():
    if not os.getenv("DEEPSEEK_API_KEY"):
        raise SystemExit(
            "API key is missing. Run from the terminal where it was configured."
        )

    benchmark = json.loads(
        (ROOT / "evaluation" / "benchmark_questions.json").read_text()
    )
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--all", action="store_true")
    options = parser.parse_args()

    selected_ids = {"Q01", "Q05", "Q13", "Q18"}
    cases = (
        benchmark["cases"]
        if options.all
        else [c for c in benchmark["cases"] if c["id"] in selected_ids]
    )
    results = []

    for case in cases:
        print(f'\n{case["id"]}: {case["question"]}')
        try:
            result = evaluate_case(case)
        except Exception as error:
            result = {
                **case,
                "status": "error",
                "error_type": type(error).__name__,
            }
        results.append(result)
        print("Status:", result["status"])
        if result.get("observed_tool"):
            print("Tool:", result["observed_tool"])
            print("Arguments:", result["observed_arguments"])
        if result.get("response_text"):
            print("Response:", result["response_text"])

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output = ROOT / "evaluation" / f"routing_smoke_{stamp}.json"
    report = {
        "evaluation_type": "First-response routing evaluation",
        "case_count": len(cases),
        "benchmark_version": benchmark["version"],
        "model_requested": os.getenv("DEEPSEEK_MODEL"),
        "base_url": os.getenv("DEEPSEEK_BASE_URL"),
        "limitations": [
            f"{len(cases)} cases; one attempt per case.",
            "Analysis tools were not executed by this evaluator.",
            "Final report accuracy and multi-turn behavior were not evaluated.",
            "Clarification and refusal wording require human review.",
        ],
        "results": results,
    }
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("\nSaved:", output.name)
    print("No overall accuracy score is calculated.")


if __name__ == "__main__":
    main()
