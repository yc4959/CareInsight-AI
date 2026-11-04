from pathlib import Path

import pandas as pd

# 根据脚本位置定位项目，不依赖终端当前所在位置。
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data" / "csv"

# 将 ID、医学代码等保留为字符串，避免误当成数字。
patients = pd.read_csv(DATA_DIR / "patients.csv", dtype="string")
procedures = pd.read_csv(DATA_DIR / "procedures.csv", dtype="string")

print("=== 患者表 ===")
print(f"记录数：{len(patients):,}")
print(f"唯一患者 ID：{patients['Id'].nunique():,}")
print(f"缺失 ID：{patients['Id'].isna().sum():,}")
print(f"重复 ID：{patients['Id'].duplicated().sum():,}")

print("\n=== 操作表 ===")
print(f"记录数：{len(procedures):,}")
print("字段：", ", ".join(procedures.columns))

# 检查每条操作是否能关联到患者表。
missing_patient = procedures["PATIENT"].isna()
unknown_patient = (
    ~missing_patient
    & ~procedures["PATIENT"].isin(patients["Id"])
)

print(f"患者 ID 缺失的操作：{missing_patient.sum():,}")
print(f"患者 ID 不在患者表中的操作：{unknown_patient.sum():,}")

# 将时间文本转换成日期，并统计无法解析的记录。
dates = pd.to_datetime(procedures["START"], errors="coerce", utc=True)
print(f"缺失或无法解析的开始时间：{dates.isna().sum():,}")
print(f"操作开始时间范围：{dates.min()} 至 {dates.max()}")

# 关键词搜索只用于发现候选记录，不是最终指标定义。
candidate_mask = procedures["DESCRIPTION"].str.contains(
    "depression screening", case=False, na=False
)
candidates = procedures.loc[candidate_mask]

summary = (
    candidates.groupby(["CODE", "DESCRIPTION"], dropna=False)
    .agg(
        record_count=("PATIENT", "size"),
        unique_patients=("PATIENT", "nunique"),
    )
    .reset_index()
    .sort_values("record_count", ascending=False)
)

print("\n=== 抑郁筛查候选记录（全部历史）===")
print(summary.to_string(index=False))
print(f"\n候选记录覆盖的独立患者：{candidates['PATIENT'].nunique():,}")

