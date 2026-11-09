"""Unified local V2 analytics flow: interpret, plan SQL, execute, verify, retry."""

import json
import os
import re

from careinsight.agent_demo import call_model
from careinsight.encounter_tool import get_substance_encounter_distribution
from careinsight.read_only_sql import run_aggregate_sql
from careinsight.repeat_tool import get_substance_repeat_summary
from careinsight.summary_tool import get_screening_summary
from careinsight.v2_encounter_pilot import _check as check_encounter
from careinsight.v2_flexible_pilot import _explicit_scope
from careinsight.v2_sql_pilot import _check_result as check_coverage

SYSTEM = """You are CareInsight's planner for Synthea synthetic procedure records.
Choose exactly one supported analysis type from the question, then call
run_aggregate_sql with a brief plan and one aggregate DuckDB SELECT. Never
invent counts or silently change the metric, grouping, year, or analysis type.
This version supports only 2020 adults. It does not measure diagnoses, actual
screening completion, causes, treatment, or real-world population patterns.

Analysis types and exact final SQL output columns:
1. coverage: metric depression or substance_use; group_by overall, age_group,
   or gender. Final columns group_name, denominator, numerator.
2. encounter_distribution: substance_use only, group_by encounter_class.
   Final columns encounter_class, procedure_records, unique_patients.
3. repeat_records: substance_use only, group_by record_frequency.
   Final columns record_frequency ('1' or '2+'), patient_count,
   procedure_records. Count procedure rows per patient first, then bucket.

Available tables/columns (CSV columns are loaded as text):
patients(Id, BIRTHDATE, DEATHDATE, GENDER)
encounters(Id, START, PATIENT, ENCOUNTERCLASS)
procedures(START, PATIENT, ENCOUNTER, CODE, DESCRIPTION)
Cast birth/death to DATE and event START to TIMESTAMPTZ. Do not use DATE_DIFF
for age. Eligible cohort: unique patients born on/before 2002-01-01, no death
record or death after 2020-12-31, and >=1 encounter START in [2020-01-01,
2021-01-01) UTC. Qualifying procedure START is in the same UTC period.
Depression codes: 171207006, 454711000124102, 715252007.
Substance use code: 713106006.
Count patients once for coverage numerator and denominator.
For gender, TRIM original GENDER and label null/blank 'Unknown'. Do not assume
only F and M. For overall, output 'All eligible adults'. For age_group, age
as of 2020-01-01: birth > 1980-01-01 => '18–39'; birth > 1955-01-01 and <=
1980-01-01 => '40–64'; birth <= 1955-01-01 => '65+'. Also apply the eligible
birth upper cutoff.
For encounter_distribution, join procedures.ENCOUNTER = encounters.Id and
verify procedures.PATIENT = encounters.PATIENT. Count qualifying procedure
rows per original ENCOUNTERCLASS and distinct procedure patients per class.
The linked encounter's START need not be in 2020; the cohort requires any
2020 encounter. Do not sum distinct patients across visit types.
For repeat_records, count each qualifying procedure row per eligible patient,
then classify each patient into '1' or '2+'; patients with no records are not
in either bucket. Do not confuse number of records with number of patients.

Use all three source tables. Do not output identifiers, SELECT *, use external
files, or modify data. A separate Pandas reference calculation verifies the
SQL result before it can be shown to the user.
"""

TOOLS = [{"type": "function", "function": {
    "name": "run_aggregate_sql",
    "description": "Execute one restricted aggregate query after selecting its analysis contract.",
    "parameters": {"type": "object", "properties": {
        "analysis_type": {"type": "string", "enum": [
            "coverage", "encounter_distribution", "repeat_records"]},
        "metric": {"type": "string", "enum": ["depression", "substance_use"]},
        "group_by": {"type": "string", "enum": [
            "overall", "age_group", "gender", "encounter_class", "record_frequency"]},
        "plan": {"type": "string"}, "sql": {"type": "string"},
    }, "required": ["analysis_type", "metric", "group_by", "plan", "sql"],
    "additionalProperties": False},
}}]


def _scope(question):
    """Reject clear scope conflicts before paying for SQL generation."""
    if not isinstance(question, str) or not question.strip():
        raise ValueError("Enter an English analysis question.")
    q = question.lower()
    years = set(re.findall(r"\b(?:19|20)\d{2}\b", q))
    if years - {"2020"}:
        raise ValueError("Only 2020 has been independently verified.")
    if re.search(r"\b(diagnos(?:is|es|ed)|prevalence|risk|cause|treatment)\b", q):
        raise ValueError("This version measures screening records, not clinical outcomes.")
    if re.search(r"\b(repeat(?:ed)?|multiple|twice)\b|more than (?:once|one)", q):
        kind = "repeat_records"
    elif (re.search(r"\b(encounter|visit)s?\b", q)
          and re.search(r"\b(type|types|where|setting|settings)\b", q)):
        kind = "encounter_distribution"
    else:
        kind = "coverage"
    if kind == "coverage":
        metric, grouping = _explicit_scope(question)
        return kind, metric, grouping
    if not re.search(r"\b(substance|drug)\b", q) or "screen" not in q:
        raise ValueError("This analysis supports substance use screening records only.")
    if "depression" in q:
        raise ValueError("Do not combine depression and substance use in one analysis.")
    if kind == "repeat_records":
        if re.search(r"\b(gender|age|men|women|male|female)\b", q):
            raise ValueError("Repeated-record breakdowns are not verified yet.")
        return kind, "substance_use", "record_frequency"
    if re.search(r"\b(gender|age|men|women|male|female)\b", q):
        raise ValueError("Encounter-type results cannot be further grouped yet.")
    return kind, "substance_use", "encounter_class"


def _parse(reply):
    calls = reply.get("tool_calls") or []
    if len(calls) != 1 or calls[0].get("function", {}).get("name") != "run_aggregate_sql":
        raise ValueError("The model did not choose one supported SQL tool.")
    try:
        args = json.loads(calls[0]["function"]["arguments"])
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid model tool arguments.") from exc
    if (not isinstance(args, dict)
            or set(args) != {"analysis_type", "metric", "group_by", "plan", "sql"}
            or args["analysis_type"] not in {"coverage", "encounter_distribution", "repeat_records"}
            or args["metric"] not in {"depression", "substance_use"}
            or args["group_by"] not in {"overall", "age_group", "gender", "encounter_class", "record_frequency"}
            or not all(isinstance(args[k], str) and args[k].strip() for k in ("plan", "sql"))):
        raise ValueError("Tool arguments do not match the analysis contract.")
    return args


def _check_repeat(query, reference):
    expected = {g["record_frequency"]: (g["patient_count"], g["procedure_records"])
                for g in reference["groups"]}
    actual = {}
    for row in query["rows"]:
        if set(row) != {"record_frequency", "patient_count", "procedure_records"}:
            raise ValueError("Repeated-record SQL output columns do not match the contract.")
        label = row["record_frequency"]
        patients, records = row["patient_count"], row["procedure_records"]
        if (label not in {"1", "2+"} or label in actual
                or type(patients) is not int or type(records) is not int
                or not 0 <= patients <= records):
            raise ValueError("Repeated-record SQL output contains invalid counts.")
        actual[label] = (patients, records)
    if actual != expected:
        raise ValueError(f"Repeated-record counts disagree with independent audit: "
                         f"generated={actual}; verified={expected}.")
    return actual


def _verify(query, scope, reference):
    kind, metric, _ = scope
    if set(query["source_tables"]) != {"patients", "encounters", "procedures"}:
        raise ValueError("The query must use the three required source tables.")
    sql = query["sql"]
    codes = ("171207006", "454711000124102", "715252007") if metric == "depression" else ("713106006",)
    if any(code not in sql for code in codes):
        raise ValueError("The query does not include every required procedure code.")
    if kind == "coverage":
        expected = {g["group"]: (g["denominator"], g["numerator"])
                    for g in reference["groups"]}
        return check_coverage(query, expected)
    if kind == "encounter_distribution":
        return check_encounter(query, reference)
    return _check_repeat(query, reference)


def analyze(question):
    scope = _scope(question)
    if not all(os.getenv(k) for k in ("DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL", "DEEPSEEK_MODEL")):
        raise RuntimeError("Model connection is not configured in this server session.")
    kind, metric, grouping = scope
    reference = (
        get_screening_summary(metric=metric, group_by=grouping) if kind == "coverage"
        else get_substance_encounter_distribution() if kind == "encounter_distribution"
        else get_substance_repeat_summary()
    )
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": question}]
    attempts = []
    for number in (1, 2):
        reply = call_model(messages, TOOLS)
        attempt = {"number": number, "status": "failed"}
        attempts.append(attempt)
        try:
            args = _parse(reply)
            attempt.update({"analysis_type": args["analysis_type"], "metric": args["metric"],
                            "group_by": args["group_by"], "plan": args["plan"], "sql": args["sql"]})
            if (args["analysis_type"], args["metric"], args["group_by"]) != scope:
                raise ValueError("Selected analysis, metric, or grouping conflicts with the question.")
            query = run_aggregate_sql(args["sql"])
            groups = _verify(query, scope, reference)
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
                                 "Your proposal failed: " + attempt["error"] +
                                 ". Call run_aggregate_sql with corrected arguments."})
            continue
        attempt["status"] = "validated"
        attempt["sql"] = query["sql"]
        return {"question": question, "analysis_type": kind, "metric": metric,
                "group_by": grouping, "plan": args["plan"], "query": query,
                "attempts": attempts, "reference": reference, "group_counts": groups}

if __name__ == "__main__":
    import sys
    question = " ".join(sys.argv[1:]).strip()
    if not question:
        raise SystemExit('Usage: python -m careinsight.v2_analysis "<English question>"')
    result = analyze(question)
    print("Question:", result["question"])
    print("Analysis type:", result["analysis_type"])
    print("Measure:", result["metric"])
    print("Grouping:", result["group_by"])
    print("Plan:", result["plan"])
    print("SQL:", result["query"]["sql"])
    print("Source tables:", ", ".join(result["query"]["source_tables"]))
    print("Independent baseline validation: PASSED")
    for attempt in result["attempts"]:
        print(f'Attempt {attempt["number"]}: {attempt["status"]}')
        if attempt.get("error"):
            print("  Reason:", attempt["error"])
    print("Verified result:")
    if result["analysis_type"] == "coverage":
        for group, (denominator, numerator) in sorted(result["group_counts"].items()):
            print(f"{group}: {numerator}/{denominator} ({numerator / denominator:.2%})")
    elif result["analysis_type"] == "encounter_distribution":
        for group, (records, patients) in sorted(result["group_counts"].items()):
            print(f"{group}: {records} records, {patients} distinct patients")
    else:
        for group, (patients, records) in sorted(result["group_counts"].items()):
            print(f"{group} record(s): {patients} patients, {records} procedure records")
