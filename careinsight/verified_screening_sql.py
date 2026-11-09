"""Reviewed SQL templates for the two 2020 adult screening-record measures.

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
    if type(year) is not int or year != 2020:
        raise ValueError("Only the reviewed 2020 cohort is available.")
    codes = ", ".join(f"'{code}'" for code in PROCEDURE_CODES[metric])
    group = GROUP_EXPRESSIONS[group_by]
    return f"""
WITH eligible AS (
    SELECT p.Id, p.GENDER,
           CASE
             WHEN CAST(p.BIRTHDATE AS DATE) > DATE '1980-01-01' THEN '18–39'
             WHEN CAST(p.BIRTHDATE AS DATE) > DATE '1955-01-01' THEN '40–64'
             ELSE '65+'
           END AS age_group
    FROM patients AS p
    WHERE CAST(p.BIRTHDATE AS DATE) <= DATE '2002-01-01'
      AND (p.DEATHDATE IS NULL
           OR CAST(p.DEATHDATE AS DATE) > DATE '2020-12-31')
      AND EXISTS (
          SELECT 1 FROM encounters AS e
          WHERE e.PATIENT = p.Id
            AND CAST(e.START AS TIMESTAMPTZ)
                >= TIMESTAMPTZ '2020-01-01 00:00:00+00'
            AND CAST(e.START AS TIMESTAMPTZ)
                < TIMESTAMPTZ '2021-01-01 00:00:00+00'
      )
), qualifying AS (
    SELECT DISTINCT pr.PATIENT
    FROM procedures AS pr
    WHERE pr.CODE IN ({codes})
      AND CAST(pr.START AS TIMESTAMPTZ)
          >= TIMESTAMPTZ '2020-01-01 00:00:00+00'
      AND CAST(pr.START AS TIMESTAMPTZ)
          < TIMESTAMPTZ '2021-01-01 00:00:00+00'
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
