import json
from pathlib import Path

from careinsight.summary_tool import get_screening_summary
from evaluation.open_benchmark import _score_saved


def test_verified_case_requires_exact_counts_and_tool():
    case = {"expected_status": "validated", "expected_tool": "run_verified_screening",
            "expected_groups": {"F": [388, 113], "M": [311, 117]}}
    outcome = {"observed_status": "validated", "tool": "run_verified_screening",
               "validation_level": "independent_metric_reference",
               "rows": [{"group_name": "F", "denominator": 388, "numerator": 113},
                        {"group_name": "M", "denominator": 311, "numerator": 117}]}
    assert _score_saved(outcome.copy(), case)["passed"]
    wrong = {**outcome, "rows": [outcome["rows"][0],
                               {"group_name": "M", "denominator": 311, "numerator": 118}]}
    assert not _score_saved(wrong, case)["passed"]
    assert not _score_saved({**outcome, "tool": "run_aggregate_sql"}, case)["passed"]


def test_exploratory_case_checks_requested_record_count():
    case = {"expected_status": "exploratory", "value_kind": "records",
            "expected_row_count": 1, "expected_counts": {"wellness": 198}}
    outcome = {"observed_status": "exploratory", "tool": "run_aggregate_sql",
               "rows": [{"encounter_class": "wellness",
                         "screening_procedure_records": 198,
                         "distinct_patients": 196}]}
    assert _score_saved(outcome, case)["passed"]
    wrong = {**outcome, "rows": [{"encounter_class": "wellness",
                                  "screening_procedure_records": 197,
                                  "distinct_patients": 198}]}
    assert not _score_saved(wrong, case)["passed"]


def test_fixed_cases_have_unique_ids_and_complete_references():
    cases = json.loads((Path(__file__).resolve().parents[1] / "evaluation" /
                        "open_benchmark_cases.json").read_text())
    assert len(cases) == 30
    assert [case["id"] for case in cases] == [f"Q{i:02d}" for i in range(1, 31)]
    for case in cases:
        if case["expected_status"] == "exploratory":
            assert len(case["expected_counts"]) == case["expected_row_count"]
        elif case["expected_status"] == "validated":
            assert case["expected_tool"] in {
                "run_verified_screening", "run_verified_screening_trend"
            }


def test_verified_case_counts_match_reference_implementation():
    cases = json.loads((Path(__file__).resolve().parents[1] / "evaluation" /
                        "open_benchmark_cases.json").read_text())
    parameters = {
        "Q14": [(2018, "depression", "overall")],
        "Q15": [(2020, "substance_use", "overall")],
        "Q16": [(2020, "depression", "age_group")],
        "Q17": [(2020, "substance_use", "gender")],
        "Q18": [(2019, "depression", "overall"),
                (2020, "depression", "overall")],
        "Q20": [(2020, "depression", "age_group")],
        "Q21": [(2020, "substance_use", "gender")],
    }
    for case in cases:
        if case["id"] not in parameters:
            continue
        actual = {}
        for year, metric, group_by in parameters[case["id"]]:
            reference = get_screening_summary(year=year, metric=metric,
                                               group_by=group_by)
            for row in reference["groups"]:
                label = str(year) if case["id"] == "Q18" else row["group"]
                actual[label] = [row["denominator"], row["numerator"]]
        assert actual == case["expected_groups"], case["id"]
