import json
from pathlib import Path

import pandas as pd

from careinsight.data_source import source_path

ROOT = Path(__file__).resolve().parents[1]


def get_screening_summary(
    year: int = 2020, group_by: str = "overall", metric: str = "depression"
) -> dict:
    """Calculate synthetic screening coverage using an allowed grouping."""
    if metric not in {"depression", "substance_use"}:
        raise ValueError("Supported metrics: depression, substance_use.")
    if group_by not in {"overall", "age_group", "gender"}:
        raise ValueError("Supported groupings: overall, age_group, gender.")
    if type(year) is not int or year not in {2019, 2020}:
        raise ValueError("Only reviewed full years 2019 and 2020 are supported.")

    patients = pd.read_csv(source_path("patients"), dtype="string")
    encounters = pd.read_csv(source_path("encounters"), dtype="string")
    procedures = pd.read_csv(source_path("procedures"), dtype="string")

    start = pd.Timestamp(f"{year}-01-01", tz="UTC")
    end = pd.Timestamp(f"{year + 1}-01-01", tz="UTC")

    encounter_dates = pd.to_datetime(encounters["START"], utc=True)
    visited = set(encounters.loc[
        (encounter_dates >= start) & (encounter_dates < end), "PATIENT"
    ])

    birth = pd.to_datetime(patients["BIRTHDATE"], errors="raise")
    death = pd.to_datetime(patients["DEATHDATE"], errors="raise")
    eligible = (
        (birth <= pd.Timestamp(f"{year - 18}-01-01"))
        & (death.isna() | (death > pd.Timestamp(f"{year}-12-31")))
        & patients["Id"].isin(visited)
    )
    cohort = patients.loc[eligible].copy()

    procedure_dates = pd.to_datetime(procedures["START"], utc=True)
    codes = {
        "depression": ("171207006", "454711000124102", "715252007"),
        "substance_use": ("713106006",),
    }[metric]
    qualifying = (
        procedures["CODE"].isin(codes)
        & (procedure_dates >= start)
        & (procedure_dates < end)
    )
    screened = set(procedures.loc[qualifying, "PATIENT"])
    cohort["screened"] = cohort["Id"].isin(screened)

    cohort_birth = birth.loc[eligible]
    before_birthday = (
        (cohort_birth.dt.month > 1) | (cohort_birth.dt.day > 1)
    )
    age = year - cohort_birth.dt.year - before_birthday.astype(int)
    cohort["age_group"] = pd.cut(
        age,
        bins=[18, 40, 65, float("inf")],
        labels=["18–39", "40–64", "65+"],
        right=False,
    )

    if cohort["age_group"].isna().any():
        raise ValueError("Some eligible patients have no age group.")

    if group_by == "overall":
        cohort["group"] = "All eligible adults"
    elif group_by == "age_group":
        cohort["group"] = cohort["age_group"].astype("string")
    else:
        cohort["group"] = (
            cohort["GENDER"].str.strip().replace("", pd.NA).fillna("Unknown")
        )

    groups = []
    for label, group in cohort.groupby("group", observed=True, sort=True):
        denominator = len(group)
        numerator = int(group["screened"].sum())
        groups.append({
            "group": str(label),
            "denominator": denominator,
            "numerator": numerator,
            "not_recorded": denominator - numerator,
            "coverage": numerator / denominator,
        })

    comparison = None
    if len(groups) >= 2:
        lowest = min(g["coverage"] for g in groups)
        highest = max(g["coverage"] for g in groups)
        comparison = {
            "lowest_groups": [
                g["group"] for g in groups if g["coverage"] == lowest
            ],
            "highest_groups": [
                g["group"] for g in groups if g["coverage"] == highest
            ],
            "gap_percentage_points": (highest - lowest) * 100,
        }

    missing_group_count = None
    if group_by == "gender":
        gender_values = cohort["GENDER"].str.strip().replace("", pd.NA)
        missing_group_count = int(gender_values.isna().sum())

    return {
        "comparison": comparison,
        "missing_group_count": missing_group_count,
        "metric_id": {
            "depression": "adult_depression_screening_record_coverage_v1",
            "substance_use": "adult_substance_use_screening_record_coverage_v1",
        }[metric],
        "metric_name": {
            "depression": "Adult depression screening record coverage",
            "substance_use": "Adult substance use screening record coverage",
        }[metric],
        "procedure_codes": list(codes),
        "definition_file": {
            "depression": "docs/metric_definition.md",
            "substance_use": "docs/substance_use_screening_metric.md",
        }[metric],
        "year": year,
        "data_source": "Synthea synthetic patient data",
        "age_as_of": f"{year}-01-01",
        "group_by": group_by,
        "group_source": {
            "overall": "All eligible adults",
            "age_group": f"Age on {year}-01-01 derived from BIRTHDATE",
            "gender": "Original GENDER field; missing values labeled Unknown",
        }[group_by],
        "denominator_definition": (
            f"Age 18+ on {year}-01-01; no recorded death or death after "
            f"{year}-12-31; at least one encounter starting in {year}. "
            "All encounter types included."
        ),
        "groups": groups,
        "limitations": [
            "Custom synthetic-data demonstration metric.",
            "Missing documentation does not prove screening was not done.",
            "Descriptive differences only; statistical significance "
            "and causes have not been established.",
        ],
    }


if __name__ == "__main__":
    print(json.dumps(get_screening_summary(), indent=2, ensure_ascii=False))
