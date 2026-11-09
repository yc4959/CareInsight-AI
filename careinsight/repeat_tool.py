"""Independent patient-level audit of repeated 2020 substance screening records."""

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def get_substance_repeat_summary():
    """Separate eligible patients with one record from those with 2+ records."""
    data = ROOT / "data" / "csv"
    patients = pd.read_csv(data / "patients.csv", dtype="string",
                           usecols=["Id", "BIRTHDATE", "DEATHDATE"])
    encounters = pd.read_csv(data / "encounters.csv", dtype="string",
                             usecols=["PATIENT", "START"])
    procedures = pd.read_csv(data / "procedures.csv", dtype="string",
                             usecols=["PATIENT", "START", "CODE"])
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
    ]
    per_patient = selected.groupby("PATIENT", observed=True).size()
    once = per_patient.loc[per_patient == 1]
    multiple = per_patient.loc[per_patient >= 2]
    return {
        "eligible_adults": len(eligible),
        "patients_with_record": int(len(per_patient)),
        "total_procedure_records": int(len(selected)),
        "groups": [
            {"record_frequency": "1", "patient_count": int(len(once)),
             "procedure_records": int(once.sum())},
            {"record_frequency": "2+", "patient_count": int(len(multiple)),
             "procedure_records": int(multiple.sum())},
        ],
        "note": "Counts describe procedure records, not confirmed screening events or diagnoses.",
    }


if __name__ == "__main__":
    import json
    print(json.dumps(get_substance_repeat_summary(), indent=2))
