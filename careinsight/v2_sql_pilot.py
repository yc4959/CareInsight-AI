"""First V2 vertical slice: model proposes SQL, tool executes, code validates."""

import json
import os

from careinsight.agent_demo import call_model
from careinsight.read_only_sql import run_aggregate_sql
from careinsight.summary_tool import get_screening_summary


QUESTION = "Compare recorded substance use screenings between men and women in 2020."

SYSTEM = """
You are CareInsight's SQL analysis planner. This is a synthetic patient dataset.
For this pilot, answer only the user's question about 2020 adult substance use
screening records by the original GENDER field. Do not supply numbers yourself.
Call run_aggregate_sql with a short plan and one DuckDB SELECT query.

Available tables and columns:
patients(Id, BIRTHDATE, DEATHDATE, GENDER)
encounters(Id, START, PATIENT, ENCOUNTERCLASS)
procedures(START, PATIENT, ENCOUNTER, CODE, DESCRIPTION)

All CSV columns are loaded as text. Explicitly CAST BIRTHDATE and DEATHDATE
AS DATE, and encounter/procedure START AS TIMESTAMPTZ before date comparisons
or DATE_DIFF. Do not apply DATE_DIFF directly to a text column.

Eligible cohort: use CAST(p.BIRTHDATE AS DATE) <= DATE '2002-01-01' to determine age 18+ on 2020-01-01. Do not use DATE_DIFF for age. Include unique patients who had no
recorded death date or a death date after 2020-12-31, and had at least one
encounter starting from 2020-01-01 inclusive to 2021-01-01 exclusive (UTC).
Numerator: eligible patients with at least one procedure with CODE 713106006
starting in the same UTC period. Count each patient once. Preserve original
GENDER labels. Join patients.Id to encounters.PATIENT and procedures.PATIENT.

The final SQL result must have exactly these columns:
group_name, denominator, numerator. One row per GENDER category. Calculate
numerator and denominator from unique patients, not procedure rows. Do not
filter to a presumed set of gender values. Do not use SELECT * in final output.
Do not access files, modify data, or call any other tool. This is a local
demonstration of query generation, not a clinical conclusion.
"""

SQL_TOOL = [{
    "type": "function",
    "function": {
        "name": "run_aggregate_sql",
        "description": "Execute a restricted aggregate SELECT query on Synthea tables.",
        "parameters": {
            "type": "object",
            "properties": {
                "plan": {"type": "string"},
                "sql": {"type": "string"},
            },
            "required": ["plan", "sql"],
            "additionalProperties": False,
        },
    },
}]


def _check_result(query_result, expected):
    """Validate shape, arithmetic, and independently computed cohort counts."""
    actual = {}
    for row in query_result["rows"]:
        if set(row) != {"group_name", "denominator", "numerator"}:
            raise ValueError("SQL output columns do not match the contract.")
        group = row["group_name"]
        denominator, numerator = row["denominator"], row["numerator"]
        if (not isinstance(group, str)
                or type(denominator) is not int or type(numerator) is not int
                or not 0 <= numerator <= denominator
                or group in actual):
            raise ValueError("SQL output has invalid group counts.")
        actual[group] = (denominator, numerator)
    if actual != expected:
        raise ValueError(
            f"Counts differ from independent baseline: generated={actual}; "
            f"verified={expected}. Check the exact age cutoff and unique patients."
        )
    return actual


def analyze(question: str = QUESTION) -> dict:
    if question != QUESTION:
        raise ValueError("This pilot supports its one reference question only.")
    if not all(os.getenv(key) for key in (
        "DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL", "DEEPSEEK_MODEL"
    )):
        raise RuntimeError("Model connection is not configured in this terminal.")

    reference = get_screening_summary(metric="substance_use", group_by="gender")
    expected = {
        row["group"]: (row["denominator"], row["numerator"])
        for row in reference["groups"]
    }
    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": question},
    ]
    attempts = []
    for attempt_number in (1, 2):
        reply = call_model(messages, SQL_TOOL)
        attempt = {"number": attempt_number, "status": "failed"}
        attempts.append(attempt)
        try:
            arguments = _parse_sql_call(reply)
            attempt["plan"] = arguments["plan"]
            attempt["sql"] = arguments["sql"]
            query_result = run_aggregate_sql(arguments["sql"])
            actual = _check_result(query_result, expected)
        except (ValueError, RuntimeError, KeyError, TypeError) as exc:
            attempt["error"] = f"{type(exc).__name__}: {exc}"
            if attempt_number == 2:
                raise RuntimeError(
                    "SQL analysis stopped after two failed attempts. "
                    f"Attempt trace: {json.dumps(attempts, ensure_ascii=False)}"
                ) from exc
            messages.append({"role": "assistant", "content": reply.get("content"),
                             "tool_calls": reply.get("tool_calls", [])})
            for call in reply.get("tool_calls") or []:
                if call.get("id"):
                    messages.append({
                        "role": "tool", "tool_call_id": call["id"],
                        "content": json.dumps({"error": attempt["error"]}),
                    })
            # Invalid or absent tool calls have no tool response to attach.
            if not reply.get("tool_calls"):
                messages.append({"role": "user", "content":
                                 f"Your proposal failed: {attempt['error']}. "
                                 "Call run_aggregate_sql with corrected plan and SQL."})
            continue
        attempt["status"] = "validated"
        attempt["sql"] = query_result["sql"]
        return {
            "question": question,
            "plan": arguments["plan"],
            "query": query_result,
            "validated": True,
            "attempts": attempts,
            "group_results": [
                {"group": group, "denominator": d, "numerator": n,
                 "coverage": n / d if d else None}
                for group, (d, n) in sorted(actual.items())
            ],
        }


def _parse_sql_call(reply):
    calls = reply.get("tool_calls") or []
    if len(calls) != 1 or calls[0]["function"]["name"] != "run_aggregate_sql":
        raise RuntimeError("The model did not propose exactly one SQL analysis.")
    try:
        arguments = json.loads(calls[0]["function"]["arguments"])
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid model tool arguments.") from exc
    if (not isinstance(arguments, dict)
            or set(arguments) != {"plan", "sql"}
            or not all(isinstance(arguments[key], str) and arguments[key].strip()
                       for key in ("plan", "sql"))):
        raise ValueError("Plan and SQL must be nonempty strings.")

    return arguments


if __name__ == "__main__":
    result = analyze()
    print("Question:", result["question"])
    print("Model plan:", result["plan"])
    print("\nGenerated SQL:\n", result["query"]["sql"])
    print("\nSource tables:", ", ".join(result["query"]["source_tables"]))
    print("Independent baseline validation: PASSED")
    for attempt in result["attempts"]:
        print(f'Attempt {attempt["number"]}: {attempt["status"]}')
        if attempt.get("error"):
            print("  Reason:", attempt["error"])
    for row in result["group_results"]:
        print(
            f'{row["group"]}: {row["numerator"]}/{row["denominator"]} '
            f'({row["coverage"]:.2%})'
        )
