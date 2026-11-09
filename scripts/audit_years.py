"""Audit yearly record coverage in the four packaged Synthea tables.

This script checks data availability. It does not validate an annual clinical
measure or infer that differences across years reflect real-world trends.
"""

from pathlib import Path

import pandas as pd

from careinsight.data_source import source_path


ROOT = Path(__file__).resolve().parents[1]
START_YEAR = 2000
END_YEAR = 2021
SCREENING_CODES = {
    "depression": {"171207006", "454711000124102", "715252007"},
    "substance_use": {"713106006"},
}


def audit_table(name: str) -> tuple[pd.DataFrame, dict]:
    columns = ["START", "PATIENT"] + (["CODE"] if name == "procedures" else [])
    frame = pd.read_csv(source_path(name), dtype="string", usecols=columns)
    dates = pd.to_datetime(frame["START"], utc=True, errors="coerce")
    year = dates.dt.year
    month = dates.dt.month
    counts = pd.DataFrame({"year": year, "month": month, "patient": frame["PATIENT"]})
    counts = counts[counts["year"].between(START_YEAR, END_YEAR)]
    annual = counts.groupby("year").agg(
        records=("patient", "size"),
        months=("month", "nunique"),
        distinct_patients=("patient", "nunique"),
    )
    if name == "procedures":
        for measure, codes in SCREENING_CODES.items():
            selected = year[frame["CODE"].isin(codes)]
            annual[f"{measure}_code_rows"] = selected.value_counts().reindex(
                annual.index, fill_value=0
            )
    quality = {
        "invalid_start": int(dates.isna().sum()),
        "missing_patient": int(frame["PATIENT"].isna().sum()),
        "last_start": dates.max().date().isoformat(),
    }
    return annual, quality


def build_report() -> str:
    audits = {name: audit_table(name) for name in (
        "encounters", "procedures", "conditions"
    )}
    rows = []
    for year in range(START_YEAR, END_YEAR + 1):
        values = [year]
        for table in ("encounters", "procedures", "conditions"):
            annual = audits[table][0]
            values.extend([
                int(annual.at[year, "records"]) if year in annual.index else 0,
                int(annual.at[year, "months"]) if year in annual.index else 0,
            ])
        procedures = audits["procedures"][0]
        values.extend([
            int(procedures.at[year, "depression_code_rows"]),
            int(procedures.at[year, "substance_use_code_rows"]),
        ])
        rows.append(values)

    assert rows[-3][0:3] == [2019, 3154, 12]
    assert rows[-2][0:3] == [2020, 3264, 12]
    assert rows[-1][0:3] == [2021, 4225, 11]
    header = (
        "| Year | Encounters | Encounter months | Procedures | Procedure months | "
        "Conditions | Condition months | Depression code rows | Substance-use code rows |"
    )
    lines = [
        "# Annual data audit: 2000–2021",
        "",
        "Source: the four packaged, approved-column tables from the public "
        "Synthea 1K sample. Run `CAREINSIGHT_USE_DEMO_DATA=1 python "
        "-m scripts.audit_years` to regenerate this report. The three event tables "
        "retain all source rows; this report selects START years 2000–2021.",
        "",
        header,
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    lines.extend("| " + " | ".join(map(str, row)) + " |" for row in rows)
    lines.extend([
        "",
        "`months` is the number of distinct calendar months containing at least "
        "one row. Twelve months of records do not establish complete observation "
        "or comparable data generation. Code counts are raw procedure rows, not "
        "unique patients or screening completion rates.",
        "",
        "## Data quality and interpretation",
        "",
    ])
    for table, (_, quality) in audits.items():
        lines.append(
            f"- `{table}`: {quality['invalid_start']} invalid START dates; "
            f"{quality['missing_patient']} missing PATIENT values; latest START "
            f"{quality['last_start']}."
        )
    lines.extend([
        "- 2021 has records in January–November only, so this sample cannot "
        "support a complete-calendar-year 2021 comparison.",
        "- Procedure volume rises sharply between 2010 and 2012 (462 to 5,905 "
        "rows). Screening-code rows rise too. The audit does not establish why "
        "this happened; it is a warning against treating the full series as a "
        "uniform clinical trend.",
        "- The current independently checked adult screening measures cover "
        "2018, 2019, and 2020 as separate annual analyses. The reviewed cross-year "
        "comparison covers 2019–2020. Extending them to another year requires "
        "year-specific cohort, code, missingness, and independent count checks.",
        "- These are synthetic records, not estimates of real population "
        "screening, diagnosis, or treatment.",
        "",
    ])
    return "\n".join(lines)


if __name__ == "__main__":
    path = ROOT / "docs" / "annual_data_audit.md"
    path.write_text(build_report())
    print(f"Saved {path}")
