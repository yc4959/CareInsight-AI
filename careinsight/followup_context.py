"""Build a short, evidence-backed context for one new analysis turn."""


def context_from_result(result):
    if result.get("status") not in {"validated", "exploratory"}:
        raise ValueError("Only a completed analysis can be followed up.")

    if result["status"] == "validated":
        attempt = result["attempts"][-1]
        params = attempt.get("parameters", {})
        metric = params.get("metric")
        if metric not in {"depression", "substance_use"}:
            raise ValueError("Verified analysis is missing its measure.")
        subject = f"adult {metric.replace('_', ' ')} screening record coverage"
        if result["tool"] == "run_verified_screening_trend":
            context_question = f"Compare {subject} in 2019 and 2020."
        else:
            year, group = params.get("year"), params.get("group_by")
            if year not in {2018, 2019, 2020} or group not in {
                "overall", "age_group", "gender"
            }:
                raise ValueError("Verified analysis is missing its year or grouping.")
            suffix = {"overall": "overall", "age_group": "by age group",
                      "gender": "by gender"}[group]
            context_question = f"Show {subject} in {year} {suffix}."
    else:
        context_question = result["question"]

    summary = (
        "Previous completed analysis: " + result["plan"] + " "
        "Tool: " + result["tool"] + ". Source tables: "
        + ", ".join(result["query"]["source_tables"]) + ". "
        "The next question requires a fresh analysis; do not copy previous counts."
    )[:2000]
    return [{"role": "user", "content": context_question[:2000]},
            {"role": "assistant", "content": summary}]
