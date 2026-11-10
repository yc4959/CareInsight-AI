"""Small live benchmark for the exploratory agent. Saves observed outcomes."""

import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from careinsight.open_analysis import analyze

ROOT = Path(__file__).resolve().parents[1]
LABEL_FIELDS = (
    "condition_description", "procedure_description", "encounter_class",
    "group_name", "DESCRIPTION", "ENCOUNTERCLASS", "CODE", "code",
)
def _counts(rows, value_kind):
    if value_kind not in {"records", "patients"}:
        raise ValueError("Benchmark case must declare records or patients.")
    output = {}
    for row in rows:
        label = next((str(row[key]) for key in LABEL_FIELDS if key in row), None)
        if label is None:
            labels = [str(value) for value in row.values() if isinstance(value, str)]
            label = labels[0] if len(labels) == 1 else None
        numbers = [key for key, value in row.items() if type(value) is int]
        if numbers == ["value"]:
            count_key = "value"
        else:
            candidates = [key for key in numbers if (
                ("record" in key.lower() and "patient" not in key.lower())
                if value_kind == "records" else
                ("patient" in key.lower() and "record" not in key.lower())
            )]
            count_key = (candidates[0] if len(candidates) == 1
                         else numbers[0] if len(numbers) == 1 else None)
        count = row[count_key] if count_key else None
        if label is None or type(count) is not int or label in output:
            raise ValueError("Benchmark cannot identify the requested count column.")
        output[label] = count
    return output


def _score_saved(outcome, case):
    """Score stored model output without making another API request."""
    if outcome["observed_status"] == "validated":
        try:
            actual = {row["group_name"]: [row["denominator"], row["numerator"]]
                      for row in outcome["rows"]}
            expected = case["expected_groups"]
            outcome["observed_groups"] = actual
            outcome["tool_ok"] = outcome.get("tool") == case["expected_tool"]
            outcome["counts_ok"] = actual == expected
            outcome["validation_ok"] = (
                outcome.get("validation_level") == "independent_metric_reference"
            )
            outcome["passed"] = (case["expected_status"] == "validated"
                                 and outcome["tool_ok"] and outcome["counts_ok"]
                                 and outcome["validation_ok"])
        except (KeyError, TypeError, ValueError) as exc:
            outcome["scoring_error"] = str(exc)
            outcome["passed"] = False
        return outcome
    if outcome["observed_status"] != "exploratory":
        expected_phrases = case.get("expected_message_contains", [])
        message = outcome.get("message", "").casefold()
        outcome["message_checks"] = {
            phrase: phrase.casefold() in message for phrase in expected_phrases
        }
        outcome["no_tool_attempted"] = not any(
            attempt.get("tool") for attempt in outcome.get("attempts", [])
        )
        outcome["passed"] = (
            outcome["observed_status"] == case["expected_status"]
            and all(outcome["message_checks"].values())
            and outcome["no_tool_attempted"]
        )
        return outcome
    try:
        actual = _counts(outcome["rows"], case["value_kind"])
        outcome["observed_counts"] = actual
        expected = case.get("expected_counts", {})
        outcome["count_checks"] = {
            label: actual.get(label) == value for label, value in expected.items()
        }
        outcome["row_count_ok"] = len(outcome["rows"]) == case["expected_row_count"]
        outcome["tool_ok"] = ("expected_tools" not in case
                              or outcome.get("tool") in case["expected_tools"])
        outcome["counts_complete"] = actual == expected
        outcome["passed"] = (
            case["expected_status"] == "exploratory"
            and outcome["row_count_ok"]
            and all(outcome["count_checks"].values())
            and outcome["tool_ok"]
            and outcome["counts_complete"]
        )
        outcome.pop("scoring_error", None)
    except (ValueError, KeyError) as exc:
        outcome["scoring_error"] = str(exc)
        outcome["passed"] = False
    return outcome


def evaluate_case(case):
    started = time.monotonic()
    outcome = {"id": case["id"], "category": case["category"],
               "question": case["question"], "expected_status": case["expected_status"]}
    try:
        result = analyze(case["question"])
        outcome["observed_status"] = result["status"]
        outcome["attempts"] = result.get("attempts", [])
        if result["status"] in {"exploratory", "validated"}:
            outcome["tool"] = result["tool"]
            outcome["plan"] = result["plan"]
            outcome["source_tables"] = result["query"]["source_tables"]
            outcome["validation_level"] = result["validation_level"]
            outcome["rows"] = result["query"]["rows"]
            outcome["query_or_parameters"] = (
                result["query"].get("sql") or result["query"].get("operation")
            )
            _score_saved(outcome, case)
        else:
            outcome["message"] = result.get("message", "")
            _score_saved(outcome, case)
    except Exception as exc:
        outcome["observed_status"] = "exception"
        outcome["error_type"] = type(exc).__name__
        outcome["passed"] = False
    outcome["seconds"] = round(time.monotonic() - started, 2)
    return outcome


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument("--start", type=int, default=1,
                        help="One-based first case number for a live run")
    parser.add_argument("--ids", nargs="+", help="Run only these case IDs")
    parser.add_argument("--rescore", type=Path,
                        help="Re-score an existing JSON report without model calls")
    args = parser.parse_args()
    cases = json.loads((ROOT / "evaluation" / "open_benchmark_cases.json").read_text())
    if args.rescore:
        source = json.loads(args.rescore.read_text())
        by_id = {case["id"]: case for case in cases}
        updated = []
        for old in source["cases"]:
            item = dict(old)
            item["previously_passed"] = old["passed"]
            updated.append(_score_saved(item, by_id[item["id"]]))
        count = sum(item["passed"] for item in updated)
        report = {"rescored_at_utc": datetime.now(timezone.utc).isoformat(),
                  "rescored_from": str(args.rescore),
                  "previous_passed": source["passed"], "total": len(updated),
                  "passed": count, "cases": updated}
        output = args.rescore.with_name(args.rescore.stem + "_rescored.json")
        output.write_text(json.dumps(report, indent=2, ensure_ascii=False))
        print(f"Corrected pass count: {count}/{len(updated)} (previously {source['passed']}/{len(updated)})")
        print("Saved:", output)
        print("Re-scoring used stored results; no model calls were made.")
        return
    missing = [name for name in (
        "DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL", "DEEPSEEK_MODEL"
    ) if not os.getenv(name)]
    if missing:
        raise SystemExit(
            "Benchmark did not start. Missing model settings in this terminal: "
            + ", ".join(missing)
        )
    if args.ids:
        by_id = {case["id"]: case for case in cases}
        unknown = set(args.ids) - set(by_id)
        if unknown:
            raise SystemExit("Unknown case IDs: " + ", ".join(sorted(unknown)))
        selected = [by_id[case_id] for case_id in args.ids]
    elif not 1 <= args.start <= len(cases):
        raise SystemExit(f"--start must be between 1 and {len(cases)}")
    elif not 1 <= args.limit <= len(cases) - args.start + 1:
        raise SystemExit(
            f"--limit must be between 1 and {len(cases) - args.start + 1} "
            f"when --start is {args.start}"
        )
    else:
        selected = cases[args.start - 1:args.start - 1 + args.limit]
    results = []
    for case in selected:
        print(f'{case["id"]}: {case["question"]}', flush=True)
        result = evaluate_case(case)
        results.append(result)
        print(f'  {"PASS" if result["passed"] else "FAIL"} · '
              f'{result["observed_status"]} · {result["seconds"]}s', flush=True)
    count = sum(item["passed"] for item in results)
    report = {"run_at_utc": datetime.now(timezone.utc).isoformat(),
              "total": len(results), "passed": count, "cases": results}
    output = ROOT / "evaluation" / (
        "open_smoke_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + ".json"
    )
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"Observed pass count: {count}/{len(results)}")
    print("Saved:", output)
    print("This is an observed smoke run, not a validated overall accuracy estimate.")


if __name__ == "__main__":
    main()
