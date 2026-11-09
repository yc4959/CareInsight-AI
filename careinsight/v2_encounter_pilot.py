"""V2 encounter-type slice: model-generated SQL checked against independent Pandas counts."""

import json
import os
import re
import sys

from careinsight.agent_demo import call_model
from careinsight.encounter_tool import get_substance_encounter_distribution
from careinsight.read_only_sql import run_aggregate_sql

SYSTEM = """You analyze synthetic Synthea records, never real patient outcomes.
For this pilot, answer only where adult substance use screening PROCEDURE RECORDS
were documented, grouped by the linked encounter's ENCOUNTERCLASS in 2020.
Call run_aggregate_sql with a short plan and one aggregate DuckDB SELECT.

Tables (all CSV columns are text):
patients(Id, BIRTHDATE, DEATHDATE, GENDER)
encounters(Id, START, PATIENT, ENCOUNTERCLASS)
procedures(START, PATIENT, ENCOUNTER, CODE, DESCRIPTION)

Eligible adults: unique patients with CAST(BIRTHDATE AS DATE) <= DATE '2002-01-01',
no recorded death or death after 2020-12-31, and at least one encounter START
in [2020-01-01, 2021-01-01) UTC. Use explicit DATE/TIMESTAMPTZ casts.
Qualifying procedure: CODE '713106006' with procedure START in the same UTC
window, belonging to an eligible patient. Join procedures.ENCOUNTER to
encounters.Id and verify procedures.PATIENT = encounters.PATIENT.

Final SELECT must have exactly encounter_class, procedure_records,
unique_patients. One row per original ENCOUNTERCLASS value; count procedure
rows and distinct procedure patients separately. Do not apply the 2020 period
filter to the linked encounter unless needed for cohort eligibility. Do not
filter to presumed encounter classes. Do not output identifiers or SELECT *.
Do not invent numbers. A code check will compare your result with an independent
Pandas calculation. Distinct patients across visit types may overlap.
"""

TOOLS = [{"type": "function", "function": {
    "name": "run_aggregate_sql",
    "description": "Run one restricted aggregate SQL query over approved Synthea tables.",
    "parameters": {"type": "object", "properties": {
        "plan": {"type": "string"}, "sql": {"type": "string"},
    }, "required": ["plan", "sql"], "additionalProperties": False},
}}]


def _parse(reply):
    calls = reply.get("tool_calls") or []
    if len(calls) != 1 or calls[0].get("function", {}).get("name") != "run_aggregate_sql":
        raise ValueError("The model did not propose one SQL analysis.")
    try:
        args = json.loads(calls[0]["function"]["arguments"])
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid model tool arguments.") from exc
    if (not isinstance(args, dict) or set(args) != {"plan", "sql"}
            or not all(isinstance(args[k], str) and args[k].strip() for k in ("plan", "sql"))):
        raise ValueError("Plan and SQL must be nonempty strings.")
    return args


def _check(query, reference):
    expected = {g["encounter_class"]: (g["procedure_records"], g["unique_patients"])
                for g in reference["groups"]}
    actual = {}
    for row in query["rows"]:
        if set(row) != {"encounter_class", "procedure_records", "unique_patients"}:
            raise ValueError("SQL output columns do not match the contract.")
        group = row["encounter_class"]
        records, patients = row["procedure_records"], row["unique_patients"]
        if (not isinstance(group, str) or group in actual
                or type(records) is not int or type(patients) is not int
                or not 0 <= patients <= records):
            raise ValueError("SQL output contains an invalid group or count.")
        actual[group] = (records, patients)
    if actual != expected:
        raise ValueError(f"SQL counts differ from independent reference: "
                         f"generated={actual}; verified={expected}.")
    if sum(r for r, _ in actual.values()) != reference["total_procedure_records"]:
        raise ValueError("Procedure record totals do not reconcile.")
    return actual


def analyze(question):
    q = question.lower()
    if (not re.search(r"\b(substance|drug)\b", q)
            or "screen" not in q
            or not re.search(r"\b(encounter|visit)\b", q)):
        raise ValueError("Ask about substance use screening records by encounter type.")
    years = set(re.findall(r"\b(?:19|20)\d{2}\b", q))
    if years - {"2020"}:
        raise ValueError("Only 2020 is verified in this pilot.")
    if not all(os.getenv(k) for k in ("DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL", "DEEPSEEK_MODEL")):
        raise RuntimeError("Model connection is not configured in this terminal.")

    reference = get_substance_encounter_distribution()
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": question}]
    attempts = []
    for number in (1, 2):
        reply = call_model(messages, TOOLS)
        attempt = {"number": number, "status": "failed"}
        attempts.append(attempt)
        try:
            args = _parse(reply)
            attempt.update({"plan": args["plan"], "sql": args["sql"]})
            query = run_aggregate_sql(args["sql"])
            actual = _check(query, reference)
        except (ValueError, RuntimeError, KeyError, TypeError) as exc:
            attempt["error"] = f"{type(exc).__name__}: {exc}"
            if number == 2:
                raise RuntimeError("Analysis stopped after two failed proposals. "
                                   + json.dumps(attempts, ensure_ascii=False)) from exc
            calls = reply.get("tool_calls") or []
            if calls and all(call.get("id") for call in calls):
                messages.append({"role": "assistant", "content": reply.get("content"),
                                 "tool_calls": calls})
                for call in calls:
                    messages.append({"role": "tool", "tool_call_id": call["id"],
                                     "content": json.dumps({"error": attempt["error"]})})
            else:
                messages.append({"role": "user", "content":
                                 "Your analysis failed: " + attempt["error"] +
                                 ". Please call run_aggregate_sql with corrected SQL."})
            continue
        attempt["status"] = "validated"
        attempt["sql"] = query["sql"]
        return {"question": question, "plan": args["plan"], "query": query,
                "attempts": attempts, "reference": reference,
                "groups": [{"encounter_class": group, "procedure_records": records,
                            "unique_patients": patients}
                           for group, (records, patients) in sorted(actual.items())]}


if __name__ == "__main__":
    question = " ".join(sys.argv[1:]).strip()
    if not question:
        raise SystemExit('Usage: python -m careinsight.v2_encounter_pilot "<English question>"')
    result = analyze(question)
    print("Question:", result["question"])
    print("Plan:", result["plan"])
    print("SQL:", result["query"]["sql"])
    print("Source tables:", ", ".join(result["query"]["source_tables"]))
    print("Independent baseline validation: PASSED")
    for item in result["attempts"]:
        print(f'Attempt {item["number"]}: {item["status"]}')
        if item.get("error"):
            print("  Reason:", item["error"])
    print("Eligible adults:", result["reference"]["eligible_adults"])
    print("Procedure records:", result["reference"]["total_procedure_records"])
    print("Unique patients overall:", result["reference"]["unique_patients_overall"])
    for row in result["groups"]:
        print(f'{row["encounter_class"]}: {row["procedure_records"]} procedure '
              f'records, {row["unique_patients"]} unique patients')
    print(result["reference"]["note"])
