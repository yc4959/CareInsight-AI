import json
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]


def get_screening_rate(year: int = 2020) -> dict:
    """Return the validated synthetic screening metric for 2020."""
    if type(year) is not int or year != 2020:
        raise ValueError("Only the validated year 2020 is supported.")

    con = duckdb.connect()
    try:
        for table in ["patients", "encounters", "procedures"]:
            con.read_csv(
                str(ROOT / "data" / "csv" / f"{table}.csv"),
                all_varchar=True,
            ).create_view(table)

        denominator, numerator = con.execute("""
            WITH eligible AS (
                SELECT DISTINCT p.Id
                FROM patients p
                WHERE CAST(p.BIRTHDATE AS DATE) <= DATE '2002-01-01'
                  AND (
                      p.DEATHDATE IS NULL
                      OR CAST(p.DEATHDATE AS DATE) > DATE '2020-12-31'
                  )
                  AND EXISTS (
                      SELECT 1 FROM encounters e
                      WHERE e.PATIENT = p.Id
                        AND CAST(e.START AS TIMESTAMPTZ)
                            >= TIMESTAMPTZ '2020-01-01 00:00:00+00'
                        AND CAST(e.START AS TIMESTAMPTZ)
                            < TIMESTAMPTZ '2021-01-01 00:00:00+00'
                  )
            ),
            screened AS (
                SELECT DISTINCT PATIENT
                FROM procedures
                WHERE CODE IN (
                    '171207006', '454711000124102', '715252007'
                )
                  AND CAST(START AS TIMESTAMPTZ)
                      >= TIMESTAMPTZ '2020-01-01 00:00:00+00'
                  AND CAST(START AS TIMESTAMPTZ)
                      < TIMESTAMPTZ '2021-01-01 00:00:00+00'
            )
            SELECT COUNT(*), COUNT(screened.PATIENT)
            FROM eligible
            LEFT JOIN screened ON eligible.Id = screened.PATIENT
        """).fetchone()
    finally:
        con.close()

    if not 0 <= numerator <= denominator:
        raise RuntimeError("Invalid numerator or denominator.")

    return {
        "metric_id": "adult_depression_screening_record_coverage_v1",
        "year": year,
        "data_source": "Synthea synthetic patient data",
        "denominator": denominator,
        "numerator": numerator,
        "not_recorded": denominator - numerator,
        "coverage": numerator / denominator if denominator else None,
        "period_start": "2020-01-01T00:00:00Z",
        "period_end_exclusive": "2021-01-01T00:00:00Z",
        "definition_file": "docs/metric_definition.md",
        "denominator_definition": (
            "Patients aged at least 18 on 2020-01-01, with no recorded "
            "death date or a death date after 2020-12-31, and at least "
            "one encounter starting in 2020. All encounter types included."
        ),
        "limitations": [
            "Custom demonstration metric, not an official quality measure.",
            "Missing documentation does not prove screening was not done.",
            "Synthetic findings do not establish real-world patterns.",
        ],
    }


if __name__ == "__main__":
    result = get_screening_rate(year=2020)
    print(json.dumps(result, indent=2, ensure_ascii=False))
