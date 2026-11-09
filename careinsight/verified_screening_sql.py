"""Reviewed SQL templates for adult screening-record measures in full years.

These templates calculate counts from the CSV tables at execution time. They
contain no saved answer values and accept only enumerated measure/group choices.
"""


PROCEDURE_CODES = {
    "depression": ("171207006", "454711000124102", "715252007"),
    "substance_use": ("713106006",),
}

GROUP_EXPRESSIONS = {
    "overall": "'All eligible adults'",
    "age_group": "eligible.age_group",
    "gender": "COALESCE(NULLIF(TRIM(eligible.GENDER), ''), 'Unknown')",
}


def build_verified_screening_sql(*, metric: str, group_by: str, year: int) -> str:
    """Return the reviewed cohort query for one supported measure and grouping."""
    if metric not in PROCEDURE_CODES:
        raise ValueError("Unsupported screening measure.")
    if group_by not in GROUP_EXPRESSIONS:
        raise ValueError("Unsupported screening grouping.")
    if type(year) is not int or year not in {2019, 2020}:
        raise ValueError("Only reviewed full years 2019 and 2020 are available.")
    codes = ", ".join(f"'{code}'" for code in PROCEDURE_CODES[metric])
    group = GROUP_EXPRESSIONS[group_by]
    birth_cutoff = f"{year - 18}-01-01"
    age_40_cutoff = f"{year - 40}-01-01"
    age_65_cutoff = f"{year - 65}-01-01"
    year_start = f"{year}-01-01 00:00:00+00"
    year_end = f"{year + 1}-01-01 00:00:00+00"
    year_last_day = f"{year}-12-31"
    return f"""
WITH eligible AS (
    SELECT p.Id, p.GENDER,
           CASE
             WHEN CAST(p.BIRTHDATE AS DATE) > DATE '{age_40_cutoff}' THEN '18–39'
             WHEN CAST(p.BIRTHDATE AS DATE) > DATE '{age_65_cutoff}' THEN '40–64'
             ELSE '65+'
           END AS age_group
    FROM patients AS p
    WHERE CAST(p.BIRTHDATE AS DATE) <= DATE '{birth_cutoff}'
      AND (p.DEATHDATE IS NULL
           OR CAST(p.DEATHDATE AS DATE) > DATE '{year_last_day}')
      AND EXISTS (
          SELECT 1 FROM encounters AS e
          WHERE e.PATIENT = p.Id
            AND CAST(e.START AS TIMESTAMPTZ)
                >= TIMESTAMPTZ '{year_start}'
            AND CAST(e.START AS TIMESTAMPTZ)
                < TIMESTAMPTZ '{year_end}'
      )
), qualifying AS (
    SELECT DISTINCT pr.PATIENT
    FROM procedures AS pr
    WHERE pr.CODE IN ({codes})
      AND CAST(pr.START AS TIMESTAMPTZ)
          >= TIMESTAMPTZ '{year_start}'
      AND CAST(pr.START AS TIMESTAMPTZ)
          < TIMESTAMPTZ '{year_end}'
)
SELECT {group} AS group_name,
       COUNT(DISTINCT eligible.Id) AS denominator,
       COUNT(DISTINCT CASE WHEN qualifying.PATIENT IS NOT NULL
                           THEN eligible.Id END) AS numerator
FROM eligible
LEFT JOIN qualifying ON qualifying.PATIENT = eligible.Id
GROUP BY group_name
ORDER BY group_name
""".strip()
