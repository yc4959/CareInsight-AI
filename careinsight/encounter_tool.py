"""Independent Pandas audit for 2020 substance-use screening record locations."""

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def get_substance_encounter_distribution():
    """Count qualifying procedure records and distinct patients per linked visit type.

    The population is the validated 2020 adult cohort. A patient may appear in
    more than one visit type, so patient counts across groups are not additive.
    """
    data = ROOT / "data" / "csv"
    patients = pd.read_csv(data / "patients.csv", dtype="string",
                           usecols=["Id", "BIRTHDATE", "DEATHDATE"])
    encounters = pd.read_csv(data / "encounters.csv", dtype="string",
                             usecols=["Id", "PATIENT", "START", "ENCOUNTERCLASS"])
    procedures = pd.read_csv(data / "procedures.csv", dtype="string",
                             usecols=["PATIENT", "ENCOUNTER", "START", "CODE"])

    start = pd.Timestamp("2020-01-01", tz="UTC")
    end = pd.Timestamp("2021-01-01", tz="UTC")
    encounter_time = pd.to_datetime(encounters["START"], utc=True, errors="raise")
    visited = set(encounters.loc[(encounter_time >= start) & (encounter_time < end),
                                 "PATIENT"])
    birth = pd.to_datetime(patients["BIRTHDATE"], errors="raise")
    death = pd.to_datetime(patients["DEATHDATE"], errors="raise")
    eligible = set(patients.loc[
        (birth <= pd.Timestamp("2002-01-01"))
        & (death.isna() | (death > pd.Timestamp("2020-12-31")))
        & patients["Id"].isin(visited), "Id"
    ])

    procedure_time = pd.to_datetime(procedures["START"], utc=True, errors="raise")
    selected = procedures.loc[
        (procedures["CODE"] == "713106006")
        & (procedure_time >= start) & (procedure_time < end)
        & procedures["PATIENT"].isin(eligible)
    ].copy()
    if encounters["Id"].duplicated().any():
        raise ValueError("Encounter IDs are not unique; distribution cannot be audited.")
    linked = selected.merge(encounters[["Id", "PATIENT", "ENCOUNTERCLASS"]],
                            left_on="ENCOUNTER", right_on="Id", how="left",
                            validate="many_to_one", suffixes=("_procedure", "_visit"))
    if linked["ENCOUNTERCLASS"].isna().any():
        raise ValueError("Some qualifying procedures lack a linked visit type.")
    if (linked["PATIENT_procedure"] != linked["PATIENT_visit"]).any():
        raise ValueError("Some procedure and linked encounter patients disagree.")
    counts = linked.groupby("ENCOUNTERCLASS", observed=True, dropna=False).agg(
        procedure_records=("ENCOUNTER", "size"),
        unique_patients=("PATIENT_procedure", "nunique"),
    )
    rows = [
        {"encounter_class": str(group),
         "procedure_records": int(record["procedure_records"]),
         "unique_patients": int(record["unique_patients"])}
        for group, record in counts.sort_index().iterrows()
    ]
    return {"year": 2020, "metric": "substance_use_screening_records",
            "eligible_adults": len(eligible),
            "total_procedure_records": len(selected),
            "unique_patients_overall": selected["PATIENT"].nunique(),
            "groups": rows,
            "note": "Distinct patient counts by visit type may overlap and must not be added."}


if __name__ == "__main__":
    import json
    print(json.dumps(get_substance_encounter_distribution(), indent=2))
