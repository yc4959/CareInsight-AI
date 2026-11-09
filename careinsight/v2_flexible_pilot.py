"""V2 pilot: model selects a measure and grouping, writes SQL, then code verifies it.

Run only locally. This is a constrained demonstration, not a public SQL service.
"""

import json
import os
import re
import sys

from careinsight.agent_demo import call_model
from careinsight.read_only_sql import run_aggregate_sql
from careinsight.summary_tool import get_screening_summary
from careinsight.v2_sql_pilot import _check_result

SYSTEM = """You are CareInsight's analytics planner for Synthea synthetic patient data.
Choose the correct screening RECORD measure and grouping from the user's question,
then call run_aggregate_sql with one short plan and one aggregate DuckDB SELECT.
Never silently substitute a different measure, grouping, or year. If the request is
ambiguous or outside scope, respond in plain English without calling a tool.
Supported year: 2020 only. Supported measures: depression screening records or
substance use screening records. These are not diagnosis or prevalence measures.
Supported groupings: overall, age_group (18–39, 40–64, 65+), gender (original
GENDER field). Do not assume F/M are the only categories.

Available tables/columns:
patients(Id, BIRTHDATE, DEATHDATE, GENDER)
encounters(Id, START, PATIENT, ENCOUNTERCLASS)
procedures(START, PATIENT, ENCOUNTER, CODE, DESCRIPTION)
All source columns are text. Cast BIRTHDATE/DEATHDATE as DATE and event START as
TIMESTAMPTZ. Do not use DATE_DIFF to decide age.

Eligible patients: unique patients with birth date <= DATE '2002-01-01', no
recorded death or death date > DATE '2020-12-31', and >=1 encounter with START
in [2020-01-01, 2021-01-01) UTC. Count each eligible patient once.
Numerator: eligible patients with >=1 procedure START in the same UTC period
and one of the measure's codes:
- depression: 171207006, 454711000124102, 715252007
- substance_use: 713106006
Do not confuse these with diagnoses.

Group labels must match:
- overall: 'All eligible adults'
- gender: TRIM(GENDER), with NULL or blank as 'Unknown'
- age_group: age on 2020-01-01: birth > 1980-01-01 => '18–39';
  birth > 1955-01-01 and <= 1980-01-01 => '40–64';
  birth <= 1955-01-01 => '65+'. Apply the cohort's upper birth cutoff too.
Final SELECT must return exactly group_name, denominator, numerator; one row
per group, no patient identifiers, no SELECT *, no file access or data changes.
Use one SQL query and never invent counts. A later code check compares your
query with an independently computed baseline before anything is reported.
"""

TOOLS = [{"type": "function", "function": {
    "name": "run_aggregate_sql",
    "description": "Run one restricted aggregate SELECT after selecting the exact measure and grouping.",
    "parameters": {"type": "object", "properties": {
        "metric": {"type": "string", "enum": ["depression", "substance_use"]},
        "group_by": {"type": "string", "enum": ["overall", "age_group", "gender"]},
        "plan": {"type": "string"}, "sql": {"type": "string"},
    }, "required": ["metric", "group_by", "plan", "sql"],
    "additionalProperties": False},
}}]


def _explicit_scope(question):
    """Guard easy-to-recognize requests; uncertain phrasing stays out of this pilot."""
    q = question.lower()
    years = set(re.findall(r"\b(?:19|20)\d{2}\b", q))
    if years - {"2020"}:
        raise ValueError("This pilot supports 2020 only; no other year was analyzed.")
    if re.search(r"\b(diagnos(?:is|es|ed)|prevalence|risk|cause|treatment)\b", q):
        raise ValueError("This pilot measures screening records, not diagnosis or clinical outcomes.")
    depression = bool(re.search(r"\bdepression\b", q))
    substance = bool(re.search(r"\b(substance|drug)\b", q))
    if depression == substance:
        raise ValueError("Specify either depression or substance use screening records.")
    if not re.search(r"\bscreen(?:ing|ings|ed)?\b", q):
        raise ValueError("Ask about screening records, not an unspecified health measure.")
    age = bool(re.search(r"\b(age|ages|younger|older)\b", q))
    gender = bool(re.search(r"\b(gender|sex|men|women|male|female)\b", q))
    overall = bool(re.search(r"\b(overall|total|all adults|how many)\b", q))
    if age and gender:
        raise ValueError("Choose one grouping for this pilot: age or gender.")
    if (age or gender) and overall:
        raise ValueError("Choose either an overall result or one grouping.")
    if not (age or gender or overall):
        raise ValueError("Specify overall, age group, or gender.")
    return ("depression" if depression else "substance_use",
            "age_group" if age else "gender" if gender else "overall")


def _proposal(reply):
    calls = reply.get("tool_calls") or []
    if len(calls) != 1 or calls[0].get("function", {}).get("name") != "run_aggregate_sql":
        raise ValueError("The model did not choose exactly one supported SQL tool.")
    try:
        args = json.loads(calls[0]["function"]["arguments"])
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid tool arguments.") from exc
    if (not isinstance(args, dict) or set(args) != {"metric", "group_by", "plan", "sql"}
            or args["metric"] not in {"depression", "substance_use"}
            or args["group_by"] not in {"overall", "age_group", "gender"}
            or not all(isinstance(args[k], str) and args[k].strip() for k in ("plan", "sql"))):
        raise ValueError("Tool arguments do not match the analysis contract.")
    return args


def analyze(question):
    if not isinstance(question, str) or not question.strip():
        raise ValueError("Enter an English analysis question.")
    metric, grouping = _explicit_scope(question)
    if not all(os.getenv(k) for k in ("DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL", "DEEPSEEK_MODEL")):
        raise RuntimeError("Model connection is not configured in this terminal.")
    reference = get_screening_summary(metric=metric, group_by=grouping)
    expected = {g["group"]: (g["denominator"], g["numerator"]) for g in reference["groups"]}
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": question}]
    attempts = []
    for number in (1, 2):
        reply = call_model(messages, TOOLS)
        attempt = {"number": number, "status": "failed"}
        attempts.append(attempt)
        try:
            args = _proposal(reply)
            attempt.update({"metric": args["metric"], "group_by": args["group_by"],
                            "plan": args["plan"], "sql": args["sql"]})
            if (args["metric"], args["group_by"]) != (metric, grouping):
                raise ValueError("Selected measure or grouping conflicts with the question.")
            result = run_aggregate_sql(args["sql"])
            actual = _check_result(result, expected)
        except (ValueError, RuntimeError, KeyError, TypeError) as exc:
            attempt["error"] = f"{type(exc).__name__}: {exc}"
            if number == 2:
                raise RuntimeError("Analysis stopped after two failed proposals. "
                                   + json.dumps(attempts, ensure_ascii=False)) from exc
            calls = reply.get("tool_calls") or []
            if calls and all(c.get("id") for c in calls):
                messages.append({"role": "assistant", "content": reply.get("content"),
                                 "tool_calls": calls})
                for call in calls:
                    messages.append({"role": "tool", "tool_call_id": call["id"],
                                     "content": json.dumps({"error": attempt["error"]})})
            else:
                messages.append({"role": "user", "content":
                                 "Your proposal failed: " + attempt["error"] +
                                 ". Call run_aggregate_sql with corrected arguments."})
            continue
        attempt["status"] = "validated"
        attempt["sql"] = result["sql"]
        return {"question": question, "metric": metric, "group_by": grouping,
                "plan": args["plan"], "query": result, "attempts": attempts,
                "groups": [{"group": g, "denominator": d, "numerator": n,
                            "coverage": n / d if d else None}
                           for g, (d, n) in sorted(actual.items())]}


if __name__ == "__main__":
    question = " ".join(sys.argv[1:]).strip()
    if not question:
        raise SystemExit('Usage: python -m careinsight.v2_flexible_pilot "<English question>"')
    output = analyze(question)
    print("Question:", output["question"])
    print("Selected measure:", output["metric"])
    print("Selected grouping:", output["group_by"])
    print("Plan:", output["plan"])
    print("SQL:", output["query"]["sql"])
    print("Source tables:", ", ".join(output["query"]["source_tables"]))
    print("Independent baseline validation: PASSED")
    for item in output["attempts"]:
        print(f'Attempt {item["number"]}: {item["status"]}')
        if item.get("error"):
            print("  Reason:", item["error"])
    for group in output["groups"]:
        print(f'{group["group"]}: {group["numerator"]}/{group["denominator"]} '
              f'({group["coverage"]:.2%})')
