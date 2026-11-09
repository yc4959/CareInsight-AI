from pathlib import Path

import pandas as pd

data = Path(__file__).resolve().parents[1] / "data" / "csv"
patients = pd.read_csv(data / "patients.csv", dtype="string")
encounters = pd.read_csv(data / "encounters.csv", dtype="string")
procedures = pd.read_csv(data / "procedures.csv", dtype="string")

start = pd.Timestamp("2020-01-01", tz="UTC")
end = pd.Timestamp("2021-01-01", tz="UTC")

encounter_dates = pd.to_datetime(encounters["START"], utc=True, errors="coerce")
visited = set(encounters.loc[
    (encounter_dates >= start) & (encounter_dates < end), "PATIENT"
])

eligible = set(patients.loc[
    (patients["BIRTHDATE"] <= "2002-01-01")
    & (patients["DEATHDATE"].isna()
       | (patients["DEATHDATE"] > "2020-12-31"))
    & patients["Id"].isin(visited),
    "Id",
])

procedure_dates = pd.to_datetime(procedures["START"], utc=True, errors="coerce")
screened = set(procedures.loc[
    (procedures["CODE"] == "713106006")
    & (procedure_dates >= start)
    & (procedure_dates < end),
    "PATIENT",
])

numerator = len(eligible & screened)
denominator = len(eligible)

assert denominator == 699
assert numerator == 230

print(f"Eligible adults: {denominator}")
print(f"With qualifying screening record: {numerator}")
print(f"No qualifying record: {denominator - numerator}")
print(f"Record coverage: {numerator / denominator:.2%}")
print("Validation passed.")
