import pytest

from careinsight.read_only_sql import run_aggregate_sql


QUERY = """
WITH eligible AS (
    SELECT p.Id, p.GENDER
    FROM patients p
    WHERE CAST(p.BIRTHDATE AS DATE) <= DATE '2002-01-01'
      AND (p.DEATHDATE IS NULL
           OR CAST(p.DEATHDATE AS DATE) > DATE '2020-12-31')
      AND EXISTS (
          SELECT 1 FROM encounters e
          WHERE e.PATIENT = p.Id
            AND CAST(e.START AS TIMESTAMPTZ)
                >= TIMESTAMPTZ '2020-01-01 00:00:00+00'
            AND CAST(e.START AS TIMESTAMPTZ)
                < TIMESTAMPTZ '2021-01-01 00:00:00+00'
      )
), screened AS (
    SELECT DISTINCT PATIENT
    FROM procedures
    WHERE CODE = '713106006'
      AND CAST(START AS TIMESTAMPTZ)
          >= TIMESTAMPTZ '2020-01-01 00:00:00+00'
      AND CAST(START AS TIMESTAMPTZ)
          < TIMESTAMPTZ '2021-01-01 00:00:00+00'
)
SELECT e.GENDER, COUNT(*) AS denominator,
       COUNT(s.PATIENT) AS numerator
FROM eligible e
LEFT JOIN screened s ON e.Id = s.PATIENT
GROUP BY e.GENDER
ORDER BY e.GENDER
"""


def test_generated_query_matches_independently_verified_counts():
    result = run_aggregate_sql(QUERY)
    assert result["source_tables"] == ["encounters", "patients", "procedures"]
    assert result["rows"] == [
        {"GENDER": "F", "denominator": 388, "numerator": 113},
        {"GENDER": "M", "denominator": 311, "numerator": 117},
    ]


@pytest.mark.parametrize("sql", [
    "SELECT 1; DROP TABLE patients",
    "DELETE FROM patients",
    "SELECT COUNT(*) FROM read_csv('/etc/passwd')",
    "SELECT Id, COUNT(*) FROM patients GROUP BY Id",
    "SELECT * FROM patients",
    "SELECT COUNT(*) FROM secret_table",
])
def test_unsafe_or_unavailable_query_is_rejected(sql):
    with pytest.raises(ValueError):
        run_aggregate_sql(sql)
