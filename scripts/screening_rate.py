from pathlib import Path
import duckdb

ROOT = Path(__file__).resolve().parents[1]
con = duckdb.connect()

# 直接读取 CSV，保留原始字符串，日期在 SQL 中明确转换。
for table in ["patients", "encounters", "procedures"]:
    con.read_csv(
        str(ROOT / "data" / "csv" / f"{table}.csv"),
        all_varchar=True,
    ).create_view(table)

# 分母：年初满 18 岁、年末仍存活、当年有就诊。
con.execute("""
CREATE TEMP TABLE eligible AS
SELECT p.Id
FROM patients p
WHERE CAST(p.BIRTHDATE AS DATE) <= DATE '2002-01-01'
  AND (
      p.DEATHDATE IS NULL
      OR CAST(p.DEATHDATE AS DATE) > DATE '2020-12-31'
  )
  AND EXISTS (
      SELECT 1
      FROM encounters e
      WHERE e.PATIENT = p.Id
        AND CAST(e.START AS TIMESTAMPTZ)
            >= TIMESTAMPTZ '2020-01-01 00:00:00+00'
        AND CAST(e.START AS TIMESTAMPTZ)
            < TIMESTAMPTZ '2021-01-01 00:00:00+00'
  )
""")

# 根据本地记录描述选取的三种代码，仅用于本项目模拟指标：
# 一般抑郁筛查、PHQ-2 筛查、PHQ-9 筛查。
# EXISTS 确保同一个人即使多次筛查，也只计一次。
con.execute("""
CREATE TEMP TABLE results AS
SELECT eligible.Id,
       EXISTS (
           SELECT 1
           FROM procedures pr
           WHERE pr.PATIENT = eligible.Id
             AND pr.CODE IN (
                 '171207006',
                 '454711000124102',
                 '715252007'
             )
             AND CAST(pr.START AS TIMESTAMPTZ)
                 >= TIMESTAMPTZ '2020-01-01 00:00:00+00'
             AND CAST(pr.START AS TIMESTAMPTZ)
                 < TIMESTAMPTZ '2021-01-01 00:00:00+00'
       ) AS has_screening
FROM eligible
""")

denominator, numerator = con.execute("""
SELECT COUNT(*),
       COUNT(*) FILTER (WHERE has_screening)
FROM results
""").fetchone()

assert 0 <= numerator <= denominator

print("2020 年成年就诊患者抑郁筛查记录覆盖率（模拟）")
print(f"分母：{denominator:,} 人")
print(f"分子：{numerator:,} 人")
print(f"未记录指定筛查：{denominator - numerator:,} 人")

if denominator:
    print(f"覆盖率：{numerator / denominator:.2%}")
else:
    print("分母为零，无法计算覆盖率。")

print("说明：合成数据、自定义指标；未记录不等于未实施。")
con.close()
