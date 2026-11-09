"""Exploratory natural-language-to-SQL analysis over synthetic Synthea tables.

The model chooses a query. Code checks SQL safety and result shape, but does not
pretend that arbitrary metric semantics have an independent reference answer.
"""

import json
import math
import os
import re
import sys
from functools import lru_cache
from pathlib import Path

import pandas as pd

import duckdb

from careinsight.model_client import call_model
from careinsight.pandas_aggregate import (
    run_pandas_aggregate,
    verify_with_independent_sql,
)
from careinsight.read_only_sql import run_aggregate_sql
from careinsight.summary_tool import get_screening_summary
from careinsight.verified_screening_sql import build_verified_screening_sql
from careinsight.data_source import source_path

SYSTEM = """You are CareInsight's data analyst for SYNTHETIC Synthea CSVs.
A user asks a descriptive question. Decide whether it can be answered from the
available tables. If yes, call one appropriate tool with a short plan. If the
question is unclear, ask one short
clarifying question in plain English without calling a tool. If it asks for
clinical advice, causation, diagnosis not represented by these tables, or an
unavailable field, explain the limit without calling a tool. Never invent data.

Available tables and columns (all CSV source columns are loaded as text):
patients(Id, BIRTHDATE, DEATHDATE, GENDER)
encounters(Id, START, PATIENT, ENCOUNTERCLASS)
procedures(START, PATIENT, ENCOUNTER, CODE, DESCRIPTION)
conditions(START, STOP, PATIENT, ENCOUNTER, CODE, DESCRIPTION)
Join encounters.PATIENT and procedures.PATIENT to patients.Id.
For a procedure's linked visit type, join procedures.ENCOUNTER to encounters.Id
and also check patient IDs match. Use DATE/TIMESTAMPTZ casts for comparisons.
A procedure row is a recorded procedure, not proof of a completed clinical
screening. Depression screening codes in this dataset: 171207006,
454711000124102, 715252007. Substance use screening procedure code: 713106006.
These code lists define local demonstration measures, not official quality
measures. If the user asks about 'adults', define age 18+ on the first day of
the requested year and state that choice in your plan. For 2020 that is birth
on/before 2002-01-01. Do not calculate age with DATE_DIFF('year',...).
If a year is absent, default to 2020 and state it in the plan. For calendar
year Y use UTC [Y-01-01, Y+1-01-01). Do not silently substitute another year.
If you define an eligible cohort, make the denominator explicit. Use distinct
patients when counting people and raw procedure rows when counting records.
The conditions table mixes disorders, findings, social factors, and other
labels. It has no reliable disease-only flag. A condition record is not proof
of disease prevalence. If a user asks which 'disease' has the most patients,
clarify whether they mean distinct patients with a new condition record in a
year, or something else. Do not silently treat all conditions as diseases.
Do not claim that a description containing '(disorder)' covers every disease.
Never answer a causal question by running a descriptive comparison instead.
If the user asks which disease is most common without defining a condition
record window, clarify before any query. Do not substitute all condition rows.
For condition questions, explain in the plan whether START means new records
in the year or START/STOP overlap means records active during the year.

Choose among three tools yourself:
- run_verified_screening for the custom 2018, 2019, or 2020 adult depression or substance-use
  screening RECORD coverage measure, overall or by age group or GENDER. Choose
  metric and group_by; the tool builds reviewed SQL from those parameters and
  independently calculates the reference cohort. It compares every group
  count before publishing. Do not
  use this tool for encounter-type procedure counts, diagnosis, 2021 or later,
  custom filters, or a different measure. A validated count is still synthetic
  and does not prove clinical screening completion.
- run_verified_screening_trend only when the user explicitly asks to compare
  2019 with 2020 for one of those two screening-record measures. It calculates
  a separate annual eligible cohort and independently checks each year's
  numerator and denominator. The percentages are descriptive and based on
  changing annual cohorts, not a longitudinal follow-up of the same people.
  2021 is incomplete in this sample (records stop in November), so do not
  compare its annual coverage with complete calendar years.
- run_pandas_aggregate for a single table with a START-year filter, one
  optional exact-value filter, one grouping, and row or unique-patient count.
  Supply table, year (0 means no filter), group_by (or 'none'), aggregation,
  filter_column (or 'none'), filter_value (or ''), and limit. This tool runs
  fixed Pandas code; do not send Python source. It sorts by count descending.
- run_aggregate_sql for joins, conditional calculations, time comparisons
  beyond one START-year filter, or other aggregate questions. SQL is parsed,
  restricted to approved tables, and executed with external access disabled.
Select the tool based on the analysis, not a predetermined answer. If one tool
cannot express the analysis, the other may be used on retry.

Only output group labels and aggregated values; never output patient or
encounter identifiers, row-level data, or SELECT *. Choose clear result column
names. Prefer at most 20 groups. Do not access files or modify data.
When clarifying an ambiguous request, keep any explicit year and ask only for
the missing subject or counting unit. Offer only supported aggregate examples;
never suggest listing or ranking individual patients.
The application will display the SQL or Pandas parameters and exact result.
Only run_verified_screening and run_verified_screening_trend may receive an independent-metric-reference label,
and only after the code check passes. Other analyses remain exploratory. Do
not claim any result is clinically validated or statistically significant.
"""

TOOLS = [{"type": "function", "function": {
    "name": "run_verified_screening",
    "description": "Calculate one reviewed 2018, 2019, or 2020 adult screening-record measure using SQL and compare all counts against an independent reference implementation. Supply measure and grouping, not SQL source.",
    "parameters": {"type": "object", "properties": {
        "metric": {"type": "string", "enum": ["depression", "substance_use"]},
        "group_by": {"type": "string", "enum": ["overall", "age_group", "gender"]},
        "year": {"type": "integer", "enum": [2018, 2019, 2020]},
        "plan": {"type": "string"},
    }, "required": ["metric", "group_by", "year", "plan"],
    "additionalProperties": False},
}}, {"type": "function", "function": {
    "name": "run_verified_screening_trend",
    "description": "Compare the same adult screening-record measure in complete calendar years 2019 and 2020. Annual cohorts and every count are independently checked. Not a same-patient longitudinal analysis.",
    "parameters": {"type": "object", "properties": {
        "metric": {"type": "string", "enum": ["depression", "substance_use"]},
        "start_year": {"type": "integer", "enum": [2019]},
        "end_year": {"type": "integer", "enum": [2020]},
        "plan": {"type": "string"},
    }, "required": ["metric", "start_year", "end_year", "plan"],
    "additionalProperties": False},
}}, {"type": "function", "function": {
    "name": "run_aggregate_sql",
    "description": "Execute one restricted exploratory aggregate SELECT over approved synthetic tables.",
    "parameters": {"type": "object", "properties": {
        "plan": {"type": "string"},
        "sql": {"type": "string"},
    }, "required": ["plan", "sql"], "additionalProperties": False},
}}, {"type": "function", "function": {
    "name": "run_pandas_aggregate",
    "description": "Parameter-based single-table Pandas grouping; no generated Python code.",
    "parameters": {"type": "object", "properties": {
        "plan": {"type": "string"},
        "table": {"type": "string", "enum": ["patients", "encounters", "procedures", "conditions"]},
        "year": {"type": "integer"},
        "group_by": {"type": "string", "enum": ["none", "GENDER", "ENCOUNTERCLASS", "CODE", "DESCRIPTION"]},
        "aggregation": {"type": "string", "enum": ["row_count", "unique_patients"]},
        "filter_column": {"type": "string", "enum": ["none", "GENDER", "ENCOUNTERCLASS", "CODE", "DESCRIPTION"]},
        "filter_value": {"type": "string"},
        "limit": {"type": "integer"},
    }, "required": ["plan", "table", "year", "group_by", "aggregation",
                    "filter_column", "filter_value", "limit"],
    "additionalProperties": False},
}}]


def _parse_call(reply):
    calls = reply.get("tool_calls") or []
    if not calls:
        return None
    if len(calls) != 1:
        raise ValueError("Expected exactly one analysis tool call.")
    name = calls[0].get("function", {}).get("name")
    if name not in {"run_verified_screening", "run_verified_screening_trend",
                    "run_aggregate_sql", "run_pandas_aggregate"}:
        raise ValueError("Unknown analysis tool.")
    try:
        args = json.loads(calls[0]["function"]["arguments"])
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid analysis tool arguments.") from exc
    if not isinstance(args, dict) or not isinstance(args.get("plan"), str) or not args["plan"].strip():
        raise ValueError("A nonempty plan is required.")
    if name == "run_verified_screening":
        if (set(args) != {"metric", "group_by", "year", "plan"}
                or args["metric"] not in {"depression", "substance_use"}
                or args["group_by"] not in {"overall", "age_group", "gender"}
                or type(args["year"]) is not int or args["year"] not in {2018, 2019, 2020}):
            raise ValueError("Verified screening arguments do not match the contract.")
    elif name == "run_verified_screening_trend":
        if (set(args) != {"metric", "start_year", "end_year", "plan"}
                or args["metric"] not in {"depression", "substance_use"}
                or type(args["start_year"]) is not int or args["start_year"] != 2019
                or type(args["end_year"]) is not int or args["end_year"] != 2020):
            raise ValueError("Verified trend arguments do not match the contract.")
    elif name == "run_aggregate_sql":
        if set(args) != {"plan", "sql"} or not isinstance(args["sql"], str) or not args["sql"].strip():
            raise ValueError("A nonempty SQL query is required.")
    else:
        if set(args) != {"plan", "table", "year", "group_by", "aggregation",
                         "filter_column", "filter_value", "limit"}:
            raise ValueError("Pandas tool arguments do not match the contract.")
    return name, args


def _validate_rows(query):
    """Generic checks only; they cannot prove the query answers the question."""
    rows = query["rows"]
    if not isinstance(rows, list) or len(rows) != query["row_count"]:
        raise ValueError("Query row count is inconsistent.")
    if not rows:
        return ["The query returned no rows; no numerical conclusion is available."]
    columns = set(rows[0])
    if not columns or any(set(row) != columns for row in rows):
        raise ValueError("Output columns are inconsistent between rows.")
    if any(name.lower() in {"id", "patient", "encounter", "patient_id", "encounter_id"}
           for name in columns):
        raise ValueError("Output appears to expose an identifier column.")
    for row in rows:
        for name, value in row.items():
            if isinstance(value, float) and not math.isfinite(value):
                raise ValueError("Output contains a nonfinite number.")
            if name.lower() in {"numerator", "denominator"}:
                if type(value) is not int or value < 0:
                    raise ValueError("Numerator and denominator must be nonnegative integers.")
        if {"numerator", "denominator"} <= columns:
            if row["numerator"] > row["denominator"]:
                raise ValueError("Numerator exceeds denominator.")
    method = query.get("method", "sql")
    execution = (
        "One parameterized Pandas aggregation over an approved synthetic table executed."
        if method == "pandas" else
        "One aggregate, read-only SQL query over approved synthetic tables executed."
    )
    return [
        execution,
        "Result shape and numeric sanity checks passed.",
        "Question-to-analysis meaning and metric definitions are not independently verified.",
    ]


def _validate_verified_screening(query, reference):
    """Require exact output shape and every independently computed group count."""
    expected = {group["group"]: (group["denominator"], group["numerator"])
                for group in reference["groups"]}
    actual = {}
    for row in query["rows"]:
        if set(row) != {"group_name", "denominator", "numerator"}:
            raise ValueError("Verified screening SQL must return group_name, denominator, numerator.")
        label = row["group_name"]
        denominator, numerator = row["denominator"], row["numerator"]
        if (not isinstance(label, str) or label in actual
                or type(denominator) is not int or type(numerator) is not int
                or not 0 <= numerator <= denominator):
            raise ValueError("Verified screening groups or counts are invalid.")
        actual[label] = (denominator, numerator)
    if actual != expected:
        raise ValueError("Generated SQL counts differ from the independent screening reference.")
    return actual


@lru_cache(maxsize=1)
def _latest_observed_year():
    """Read the latest START year actually present in the local event tables."""
    latest = []
    for table in ("encounters", "procedures", "conditions"):
        starts = pd.read_csv(source_path(table), usecols=["START"], dtype="string")["START"]
        years = pd.to_numeric(starts.str.slice(0, 4), errors="coerce")
        if years.notna().any():
            latest.append(int(years.max()))
    if not latest:
        raise RuntimeError("No dated records are available for analysis.")
    return max(latest)


def _requested_years(question, history):
    """Latest explicit user year wins; otherwise retain the prior user year."""
    utterances = [question] + [item["content"] for item in reversed(history)
                               if item["role"] == "user"]
    for utterance in utterances:
        years = {int(value) for value in re.findall(
            r"(?<![0-9])(?:19|20)[0-9]{2}(?![0-9])", utterance
        )}
        if years:
            return years
    return set()


def _verified_request_matches(question, history, args):
    """Prevent a verified tool from silently changing the requested measure."""
    user_text = " ".join(
        [item["content"] for item in history if item["role"] == "user"]
        + [question]
    ).lower()
    years = _requested_years(question, history)
    if (years and years != {args["year"]}) or (not years and args["year"] != 2020):
        return False
    if re.search(r"\b(diagnos(?:is|es|ed)|prevalence|cause|treatment)\b", user_text):
        return False
    depression = bool(re.search(r"\bdepression\b", user_text))
    substance = bool(re.search(r"\b(substance|drug)\b", user_text))
    if depression == substance:
        return False
    if args["metric"] != ("depression" if depression else "substance_use"):
        return False
    if not re.search(r"\bscreen(?:ing|ings|ed)?\b", user_text):
        return False
    if re.search(r"\b(encounter|visit)\b", user_text) and re.search(
        r"\b(type|class|where)\b", user_text
    ):
        return False
    age = bool(re.search(r"\b(age|ages|younger|older)\b", user_text))
    gender = bool(re.search(r"\b(gender|sex|men|women|male|female)\b", user_text))
    if age and gender:
        return False
    group = "age_group" if age else "gender" if gender else "overall"
    return args["group_by"] == group


def _verified_trend_request_matches(question, history, args):
    """Require an explicit two-year screening comparison before using the trend tool."""
    user_text = " ".join(
        [item["content"] for item in history if item["role"] == "user"]
        + [question]
    ).lower()
    if _requested_years(question, history) != {2019, 2020}:
        return False
    if re.search(r"\b(diagnos(?:is|es|ed)|prevalence|cause|treatment)\b", user_text):
        return False
    if not re.search(r"\bscreen(?:ing|ings|ed)?\b", user_text):
        return False
    if not re.search(r"\b(change|trend|compare|comparison|difference|between|versus|vs)\b", user_text):
        return False
    depression = bool(re.search(r"\bdepression\b", user_text))
    substance = bool(re.search(r"\b(substance|drug)\b", user_text))
    if depression == substance:
        return False
    return args["metric"] == ("depression" if depression else "substance_use")


def _request_boundary(question):
    """Require clarification for meanings this data cannot safely infer."""
    q = question.lower()
    if re.search(r"\b(cause|caused|causes|causal|why|because|reason|reasons)\b", q) or any(
        word in q for word in ("为什么", "原因", "导致", "因果")
    ):
        return (
            "These synthetic records can describe differences but cannot show "
            "what caused them. If you want a descriptive comparison, ask for "
            "record counts or percentages instead. No analysis was run."
        )
    disease = bool(re.search(r"\b(disease|diseases|illness|illnesses)\b", q)
                   or any(word in q for word in ("疾病", "患病")))
    defined_record = bool(re.search(r"\b(condition records?|disorder-labeled|recorded conditions?)\b", q)
                          or "条件记录" in q)
    if disease and not defined_record:
        return (
            "The conditions table includes findings and social factors, so it "
            "is not a disease-only list. Do you mean distinct patients with a "
            "new condition record starting in the year, or with a record active "
            "during the year? Please choose a record definition before analysis."
        )
    return None


def _reviewed_plan(tool_name, args, reference):
    """Describe the rules that the reviewed SQL actually executed."""
    years = (2019, 2020) if tool_name == "run_verified_screening_trend" else (args["year"],)
    year_label = " and ".join(str(year) for year in years)
    cohort_rules = "; ".join(
        f"{year}: born on or before {year - 18}-01-01, no recorded death "
        f"through {year}-12-31, and at least one encounter starting in "
        f"UTC [{year}-01-01, {year + 1}-01-01)"
        for year in years
    )
    group = ("calendar year" if len(years) == 2 else {
        "overall": "all eligible adults",
        "age_group": "age group (18–39, 40–64, 65+)",
        "gender": "the original GENDER values",
    }[args["group_by"]])
    codes = ", ".join(reference["procedure_codes"])
    description = (
        f"Count distinct eligible adults and distinct adults with at least one "
        f"qualifying {args['metric'].replace('_', ' ')} screening procedure "
        f"record (codes {codes}) for {year_label}, grouped by {group}. "
        f"Annual cohort rules: {cohort_rules}. Compare every numerator and "
        f"denominator with the independent reference."
    )
    if len(years) == 2:
        description += " The two annual cohorts may contain different people."
    return description


def analyze(question, history=None):
    if not isinstance(question, str) or not question.strip():
        raise ValueError("Enter an English analysis question.")
    if history is None:
        history = []
    if (not isinstance(history, list) or len(history) > 6
            or any(not isinstance(item, dict)
                   or set(item) != {"role", "content"}
                   or item["role"] not in {"user", "assistant"}
                   or not isinstance(item["content"], str)
                   or len(item["content"]) > 2000
                   for item in history)):
        raise ValueError("Invalid clarification history.")
    years = _requested_years(question, history)
    latest_year = _latest_observed_year()
    unavailable = sorted(year for year in years if year > latest_year)
    if unavailable:
        return {"status": "no_analysis", "question": question,
                "message": ("The local synthetic data have no dated encounter, procedure, "
                            f"or condition records after {latest_year}. Requested "
                            f"year(s): {', '.join(map(str, unavailable))}. "
                            "No analysis was run; please choose a year covered "
                            "by this dataset."),
                "attempts": []}
    boundary = _request_boundary(question)
    if boundary:
        return {"status": "no_analysis", "question": question,
                "message": boundary, "attempts": []}
    if not all(os.getenv(k) for k in ("DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL", "DEEPSEEK_MODEL")):
        raise RuntimeError("Model connection is not configured in this terminal.")
    messages = ([{"role": "system", "content": SYSTEM}] + history
                + [{"role": "user", "content": question.strip()}])
    attempts = []
    for number in (1, 2):
        reply = call_model(messages, TOOLS)
        attempt = {"number": number, "status": "failed"}
        attempts.append(attempt)
        try:
            proposal = _parse_call(reply)
            if proposal is None:
                return {"status": "no_analysis", "question": question,
                        "message": reply.get("content") or
                        "I need a clearer question before running an analysis.",
                        "attempts": attempts[:-1]}
            tool_name, args = proposal
            attempt.update({"tool": tool_name, "plan": args["plan"]})
            reference = None
            if tool_name == "run_verified_screening":
                if not _verified_request_matches(question, history, args):
                    raise ValueError("Verified measure or grouping does not match the user's request.")
                reference = get_screening_summary(
                    year=args["year"], metric=args["metric"],
                    group_by=args["group_by"],
                )
                attempt["parameters"] = {
                    "year": args["year"], "metric": args["metric"],
                    "group_by": args["group_by"],
                }
                sql = build_verified_screening_sql(
                    year=args["year"], metric=args["metric"],
                    group_by=args["group_by"],
                )
                query = run_aggregate_sql(sql)
            elif tool_name == "run_verified_screening_trend":
                if not _verified_trend_request_matches(question, history, args):
                    raise ValueError("The requested years or screening measure do not match the trend tool.")
                annual = []
                sql_parts = []
                rows = []
                for year in (2019, 2020):
                    annual_reference = get_screening_summary(
                        year=year, metric=args["metric"], group_by="overall"
                    )
                    sql = build_verified_screening_sql(
                        year=year, metric=args["metric"], group_by="overall"
                    )
                    annual_query = run_aggregate_sql(sql)
                    _validate_verified_screening(annual_query, annual_reference)
                    annual.append(annual_reference)
                    annual_row = annual_query["rows"][0]
                    rows.append({"group_name": str(year),
                                 "denominator": annual_row["denominator"],
                                 "numerator": annual_row["numerator"]})
                    sql_parts.append(f"-- Executed for {year}\n{annual_query['sql']}")
                query = {"sql": "\n\n".join(sql_parts),
                         "source_tables": ["encounters", "patients", "procedures"],
                         "row_count": len(rows), "rows": rows}
                reference = {"metric_name": annual[0]["metric_name"],
                             "procedure_codes": annual[0]["procedure_codes"],
                             "year": "2019–2020", "trend": True,
                             "groups": [{"group": row["group_name"],
                                         "denominator": row["denominator"],
                                         "numerator": row["numerator"]} for row in rows],
                             "denominator_definition": (
                                 "Each year has its own cohort: age 18+ on January 1, "
                                 "no recorded death through December 31, and at least "
                                 "one encounter starting that calendar year. The cohorts "
                                 "may differ between years. 2021 is incomplete in this sample."
                             )}
                attempt["parameters"] = {"metric": args["metric"],
                                         "start_year": 2019, "end_year": 2020}
            elif tool_name == "run_aggregate_sql":
                attempt["sql"] = args["sql"]
                query = run_aggregate_sql(args["sql"])
            else:
                params = {key: value for key, value in args.items() if key != "plan"}
                attempt["parameters"] = params
                query = run_pandas_aggregate(**params)
            checks = _validate_rows(query)
            if reference is not None:
                _validate_verified_screening(query, reference)
                checks = [check for check in checks if not check.startswith(
                    "Question-to-analysis meaning and metric definitions"
                )]
                checks.append(
                    "The selected measure and grouping matched the request, and all "
                    "group counts matched independently calculated annual references."
                )
            cross_check = None
            if tool_name == "run_pandas_aggregate":
                cross_check = verify_with_independent_sql(query)
                checks.append(
                    "Pandas counts matched an independently executed DuckDB query "
                    "using the same selected parameters."
                )
        except (ValueError, RuntimeError, KeyError, TypeError, duckdb.Error) as exc:
            attempt["error"] = f"{type(exc).__name__}: {exc}"
            if number == 2:
                return {"status": "failed", "question": question,
                        "message": "No result was published after two failed analysis attempts.",
                        "attempts": attempts}
            calls = reply.get("tool_calls") or []
            if calls and all(call.get("id") for call in calls):
                messages.append({"role": "assistant", "content": reply.get("content"),
                                 "tool_calls": calls})
                for call in calls:
                    messages.append({"role": "tool", "tool_call_id": call["id"],
                                     "content": json.dumps({"error": attempt["error"]})})
            else:
                messages.append({"role": "user", "content":
                                 "Your proposal could not run: " + attempt["error"] +
                                 ". Correct the analysis and call one available tool."})
            continue
        attempt["status"] = "validated" if reference is not None else "executed"
        display_plan = (
            _reviewed_plan(tool_name, args, reference)
            if reference is not None else args["plan"]
        )
        attempt["plan"] = display_plan
        if tool_name in {"run_aggregate_sql", "run_verified_screening",
                         "run_verified_screening_trend"}:
            attempt["sql"] = query["sql"]
        return {"status": "validated" if reference is not None else "exploratory",
                "question": question,
                "plan": display_plan, "tool": tool_name, "query": query,
                "checks": checks, "attempts": attempts,
                "cross_check": cross_check,
                "metric_reference": reference,
                "validation_level": (
                    "independent_metric_reference" if reference is not None else
                    "cross_tool_numeric" if cross_check else "structural_only"
                )}


if __name__ == "__main__":
    question = " ".join(sys.argv[1:]).strip()
    if not question:
        raise SystemExit('Usage: python -m careinsight.open_analysis "<English question>"')
    output = analyze(question)
    print("Status:", output["status"])
    if output["status"] in {"exploratory", "validated"}:
        print("Selected tool:", output["tool"])
        print("Plan:", output["plan"])
        if output["tool"] in {"run_aggregate_sql", "run_verified_screening"}:
            print("SQL:", output["query"]["sql"])
        else:
            print("Pandas parameters:", json.dumps(output["query"]["operation"], ensure_ascii=False))
        print("Source tables:", ", ".join(output["query"]["source_tables"]))
        print("Rows:", json.dumps(output["query"]["rows"], ensure_ascii=False, indent=2))
        print("Validation level:", output["validation_level"])
        if output["cross_check"]:
            print("Cross-tool numeric check: PASSED")
        if output["status"] == "validated":
            print("All group counts matched the independent screening reference.")
        else:
            print("Question-to-analysis meaning is not independently verified.")
        for check in output["checks"]:
            print("-", check)
    else:
        print(output["message"])
    for attempt in output["attempts"]:
        print(f'Attempt {attempt["number"]}: {attempt["status"]}')
        if attempt.get("error"):
            print("  Reason:", attempt["error"])
