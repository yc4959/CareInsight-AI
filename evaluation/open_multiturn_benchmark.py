"""Run two live clarification conversations against the exploratory agent."""

import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from careinsight.open_analysis import analyze
from evaluation.open_benchmark import _score_saved


ROOT = Path(__file__).resolve().parents[1]


def run_case(case, saved_first=None):
    started = time.monotonic()
    outcome = {"id": case["id"], "question": case["question"],
               "answer": case["answer"]}
    try:
        first = (analyze(case["question"]) if saved_first is None else {
            "status": saved_first["status"],
            "message": saved_first["message"],
            "attempts": [],
        })
        message = first.get("message", "")
        checks = {phrase: phrase.casefold() in message.casefold()
                  for phrase in case["clarification_contains"]}
        alternatives = case.get("clarification_any", [])
        any_check = (not alternatives or any(
            phrase.casefold() in message.casefold() for phrase in alternatives
        ))
        first_ok = (first["status"] == "no_analysis"
                    and all(checks.values()) and any_check
                    and not any(a.get("tool") for a in first.get("attempts", [])))
        outcome["first_turn"] = {
            "status": first["status"], "message": message,
            "message_checks": checks, "clarification_any_passed": any_check,
            "no_tool_attempted":
            not any(a.get("tool") for a in first.get("attempts", [])),
            "passed": first_ok,
        }
        if first_ok:
            history = [{"role": "user", "content": case["question"]},
                       {"role": "assistant", "content": message}]
            second = analyze(case["answer"], history=history)
            followup = {"observed_status": second["status"],
                        "attempts": second.get("attempts", []),
                        "message": second.get("message", "")}
            if second["status"] == "exploratory":
                followup.update({"tool": second["tool"], "plan": second["plan"],
                                 "rows": second["query"]["rows"],
                                 "source_tables": second["query"]["source_tables"],
                                 "query_or_parameters": second["query"].get("sql")
                                 or second["query"].get("operation")})
            _score_saved(followup, case)
            outcome["followup"] = followup
        outcome["passed"] = first_ok and outcome.get("followup", {}).get("passed", False)
    except Exception as exc:
        outcome["passed"] = False
        outcome["error_type"] = type(exc).__name__
        outcome["error"] = str(exc)[:500]
    outcome["seconds"] = round(time.monotonic() - started, 2)
    return outcome


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ids", nargs="+", help="Run only these case IDs")
    parser.add_argument("--resume", type=Path,
                        help="Reuse saved first-turn clarifications; run follow-ups live")
    args = parser.parse_args()
    missing = [name for name in ("DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL",
                                 "DEEPSEEK_MODEL") if not os.getenv(name)]
    if missing:
        raise SystemExit("Benchmark did not start. Missing model settings: "
                         + ", ".join(missing))
    cases = json.loads((ROOT / "evaluation" / "open_multiturn_cases.json").read_text())
    saved_by_id = {}
    if args.resume:
        saved = json.loads(args.resume.read_text())
        saved_by_id = {item["id"]: item.get("first_turn")
                       for item in saved["cases"]}
    if args.ids:
        by_id = {case["id"]: case for case in cases}
        unknown = set(args.ids) - set(by_id)
        if unknown:
            raise SystemExit("Unknown case IDs: " + ", ".join(sorted(unknown)))
        cases = [by_id[case_id] for case_id in args.ids]
    results = []
    for case in cases:
        print(f'{case["id"]}: {case["question"]}', flush=True)
        if args.resume and not saved_by_id.get(case["id"]):
            raise SystemExit("Saved report has no first turn for " + case["id"])
        result = run_case(case, saved_first=saved_by_id.get(case["id"]))
        if args.resume:
            result["first_turn_reused_from"] = str(args.resume)
        results.append(result)
        print(f'  {"PASS" if result["passed"] else "FAIL"} · '
              f'{result["seconds"]}s', flush=True)
    now = datetime.now(timezone.utc)
    output = ROOT / "evaluation" / (
        "open_multiturn_" + now.strftime("%Y%m%dT%H%M%SZ") + ".json")
    report = {"run_at_utc": now.isoformat(), "total": len(results),
              "passed": sum(item["passed"] for item in results), "cases": results}
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(f'Observed pass count: {report["passed"]}/{report["total"]}')
    print("Saved:", output)
    print("This is a small live multi-turn test, not an overall accuracy estimate.")


if __name__ == "__main__":
    main()
