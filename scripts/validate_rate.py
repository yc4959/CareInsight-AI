from pathlib import Path
import runpy
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "csv"

patients = pd.read_csv(DATA / "patients.csv", dtype="string")
encounters = pd.read_csv(DATA / "encounters.csv", dtype="string")
procedures = pd.read_csv(DATA / "procedures.csv", dtype="string")

birth = pd.to_datetime(patients["BIRTHDATE"], errors="raise")
death = pd.to_datetime(patients["DEATHDATE"], errors="raise")

start = pd.Timestamp("2020-01-01", tz="UTC")
end = pd.Timestamp("2021-01-01", tz="UTC")

# 用集合保存独立患者，每个 ID 只出现一次。
encounter_dates = pd.to_datetime(encounters["START"], utc=True)
visited_ids = set(
    encounters.loc[
        (encounter_dates >= start) & (encounter_dates < end),
        "PATIENT",
    ]
)

eligible_mask = (
    (birth <= pd.Timestamp("2002-01-01"))
    & (death.isna() | (death > pd.Timestamp("2020-12-31")))
    & patients["Id"].isin(visited_ids)
)
eligible_ids = set(patients.loc[eligible_mask, "Id"])

procedure_dates = pd.to_datetime(procedures["START"], utc=True)
screening_mask = (
    procedures["CODE"].isin(
        ["171207006", "454711000124102", "715252007"]
    )
    & (procedure_dates >= start)
    & (procedure_dates < end)
)
screened_ids = set(procedures.loc[screening_mask, "PATIENT"])

# 交集：既符合分母条件，又有筛查记录的人。
numerator = len(eligible_ids & screened_ids)
denominator = len(eligible_ids)

# 重新运行已有 SQL 脚本，取得本次计算结果。
sql_result = runpy.run_path(str(ROOT / "scripts" / "screening_rate.py"))

assert denominator == sql_result["denominator"], "分母不一致"
assert numerator == sql_result["numerator"], "分子不一致"

print("\n=== Pandas 独立复算 ===")
print(f"分母：{denominator} 人")
print(f"分子：{numerator} 人")
print("验证通过：Pandas 与 SQL 的分子、分母完全一致。")
