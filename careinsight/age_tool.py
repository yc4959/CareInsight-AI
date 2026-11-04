import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def get_screening_by_age(year: int = 2020) -> dict:
    """Calculate screening record coverage by age for synthetic patients."""
    if type(year) is not int or year != 2020:
        raise ValueError("Only the validated year 2020 is supported.")

    data = ROOT / "data" / "csv"
    patients = pd.read_csv(data / "patients.csv", dtype="string")
    encounters = pd.read_csv(data / "encounters.csv", dtype="string")
    procedures = pd.read_csv(data / "procedures.csv", dtype="string")

    start = pd.Timestamp("2020-01-01", tz="UTC")
    end = pd.Timestamp("2021-01-01", tz="UTC")

    encounter_dates = pd.to_datetime(encounters["START"], utc=True)
    visited = set(encounters.loc[
        (encounter_dates >= start) & (encounter_dates < end), "PATIENT"
    ])

    birth = pd.to_datetime(patients["BIRTHDATE"], errors="raise")
    death = pd.to_datetime(patients["DEATHDATE"], errors="raise")
    eligible = (
        (birth <= pd.Timestamp("2002-01-01"))
        & (death.isna() | (death > pd.Timestamp("2020-12-31")))
        & patients["Id"].isin(visited)
    )
    cohort = patients.loc[eligible].copy()

    procedure_dates = pd.to_datetime(procedures["START"], utc=True)
    qualifying = (
        procedures["CODE"].isin([
            "171207006", "454711000124102", "715252007"
        ])
        & (procedure_dates >= start)
        & (procedure_dates < end)
    )
    screened = set(procedures.loc[qualifying, "PATIENT"])
    cohort["screened"] = cohort["Id"].isin(screened)

    cohort_birth = birth.loc[eligible]
    before_birthday = (
        (cohort_birth.dt.month > 1) | (cohort_birth.dt.day > 1)
    )
    age = 2020 - cohort_birth.dt.year - before_birthday.astype(int)
    cohort["age_group"] = pd.cut(
        age,
        bins=[18, 40, 65, float("inf")],
        labels=["18–39", "40–64", "65+"],
        right=False,
    )

    if cohort["age_group"].isna().any():
        raise ValueError("Some eligible patients have no age group.")

    groups = []
    for label, group in cohort.groupby("age_group", observed=True):
        denominator = len(group)
        numerator = int(group["screened"].sum())
        groups.append({
            "age_group": str(label),
            "denominator": denominator,
            "numerator": numerator,
            "not_recorded": denominator - numerator,
            "coverage": numerator / denominator,
        })

    return {
        "metric_id": "adult_depression_screening_record_coverage_v1",
        "year": year,
        "data_source": "Synthea synthetic patient data",
        "age_as_of": "2020-01-01",
        "denominator_definition": (
            "Age 18+ on 2020-01-01; no recorded death or death after "
            "2020-12-31; at least one encounter starting in 2020. "
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
    print(json.dumps(get_screening_by_age(), indent=2, ensure_ascii=False))
