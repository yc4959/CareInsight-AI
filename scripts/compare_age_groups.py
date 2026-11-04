from pathlib import Path
import runpy
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

# 运行验证脚本，并复用其中已检查的数据与患者集合。
validated = runpy.run_path(str(ROOT / "scripts" / "validate_rate.py"))
patients = validated["patients"]
eligible_ids = validated["eligible_ids"]
screened_ids = validated["screened_ids"]

cohort = patients.loc[patients["Id"].isin(eligible_ids)].copy()
birth = pd.to_datetime(cohort["BIRTHDATE"], errors="raise")

# 计算截至 2020-01-01 已满的周岁。
birthday_not_reached = (birth.dt.month > 1) | (birth.dt.day > 1)
cohort["age"] = 2020 - birth.dt.year - birthday_not_reached.astype(int)

cohort["age_group"] = pd.cut(
    cohort["age"],
    bins=[18, 40, 65, float("inf")],
    labels=["18–39", "40–64", "65+"],
    right=False,
)

cohort["has_screening"] = cohort["Id"].isin(screened_ids)

assert cohort["age_group"].notna().all(), "存在未分配年龄组的患者"

summary = (
    cohort.groupby("age_group", observed=True)
    .agg(
        eligible=("Id", "size"),
        screened=("has_screening", "sum"),
    )
)

summary["not_recorded"] = summary["eligible"] - summary["screened"]
summary["rate_pct"] = 100 * summary["screened"] / summary["eligible"]

# 分组结果必须能加回总体结果。
assert summary["eligible"].sum() == validated["denominator"]
assert summary["screened"].sum() == validated["numerator"]

print("\n=== 2020 年年龄组比较（合成数据）===")
print(summary.to_string(float_format=lambda x: f"{x:.2f}"))
print("\n检查通过：各组分子、分母之和与总体一致。")
print("注意：这里展示的是描述性差异，尚未评估差异的不确定性。")
