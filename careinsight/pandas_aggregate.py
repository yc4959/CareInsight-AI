"""Constrained Pandas aggregate tool for exploratory Synthea questions.

The model supplies data parameters, never Python code. Single-table only;
questions requiring joins should use the restricted SQL tool.
"""

from pathlib import Path

import pandas as pd

from careinsight.data_source import source_path

ROOT = Path(__file__).resolve().parents[1]
COLUMNS = {
    "patients": {"Id", "BIRTHDATE", "DEATHDATE", "GENDER"},
    "encounters": {"Id", "START", "PATIENT", "ENCOUNTERCLASS"},
    "procedures": {"START", "PATIENT", "ENCOUNTER", "CODE", "DESCRIPTION"},
    "conditions": {"START", "STOP", "PATIENT", "ENCOUNTER", "CODE", "DESCRIPTION"},
}
GROUP_COLUMNS = {"GENDER", "ENCOUNTERCLASS", "CODE", "DESCRIPTION", "none"}
FILTER_COLUMNS = {"GENDER", "ENCOUNTERCLASS", "CODE", "DESCRIPTION", "none"}


def run_pandas_aggregate(*, table, year, group_by, aggregation,
                         filter_column="none", filter_value="", limit=20):
    """Read one approved table and return row or distinct-patient counts."""
    if table not in COLUMNS:
        raise ValueError("Table is not available.")
    if type(year) is not int or not 0 <= year <= 9999:
        raise ValueError("Year must be an integer; use 0 for no date filter.")
    if year and (table == "patients" or not 1900 <= year <= 2100):
        raise ValueError("This table cannot use the requested START year filter.")
    if group_by not in GROUP_COLUMNS or (group_by != "none" and group_by not in COLUMNS[table]):
        raise ValueError("Grouping column is not available on this table.")
    if aggregation not in {"row_count", "unique_patients"}:
        raise ValueError("Unsupported aggregation.")
    if aggregation == "unique_patients" and "PATIENT" not in COLUMNS[table]:
        raise ValueError("Distinct-patient counts need encounters or procedures.")
    if filter_column not in FILTER_COLUMNS or (filter_column != "none" and filter_column not in COLUMNS[table]):
        raise ValueError("Filter column is not available on this table.")
    if not isinstance(filter_value, str) or len(filter_value) > 200:
        raise ValueError("Invalid filter value.")
    if (filter_column == "none") != (filter_value == ""):
        raise ValueError("A filter column and value must be supplied together.")
    if type(limit) is not int or not 1 <= limit <= 50:
        raise ValueError("Limit must be between 1 and 50.")

    selected_columns = set()
    if group_by != "none":
        selected_columns.add(group_by)
    if filter_column != "none":
        selected_columns.add(filter_column)
    if year:
        selected_columns.add("START")
    if aggregation == "unique_patients":
        selected_columns.add("PATIENT")
    if not selected_columns:
        selected_columns.add("Id" if table == "patients" else "START")
    frame = pd.read_csv(source_path(table),
                        dtype="string", usecols=sorted(selected_columns))
    if year:
        timestamps = pd.to_datetime(frame["START"], utc=True, errors="raise")
        start = pd.Timestamp(f"{year:04d}-01-01", tz="UTC")
        end = pd.Timestamp(f"{year + 1:04d}-01-01", tz="UTC")
        frame = frame.loc[(timestamps >= start) & (timestamps < end)]
    if filter_column != "none":
        frame = frame.loc[frame[filter_column] == filter_value]
    if group_by == "none":
        value = (len(frame) if aggregation == "row_count"
                 else frame["PATIENT"].nunique())
        rows = [{"group_name": "All matching records", "value": int(value)}]
    else:
        groups = frame[group_by].fillna("Unknown").replace("", "Unknown")
        frame = frame.assign(_group_name=groups)
        if aggregation == "row_count":
            counts = frame.groupby("_group_name", dropna=False, observed=True).size()
        else:
            counts = frame.groupby("_group_name", dropna=False, observed=True)["PATIENT"].nunique()
        ordered = sorted(((str(label), int(value)) for label, value in counts.items()),
                         key=lambda item: (-item[1], item[0]))[:limit]
        rows = [{"group_name": label, "value": value} for label, value in ordered]
    return {
        "method": "pandas",
        "source_tables": [table],
        "row_count": len(rows),
        "rows": rows,
        "value_label": aggregation,
        "operation": {"table": table, "year": year, "group_by": group_by,
                      "aggregation": aggregation, "filter_column": filter_column,
                      "filter_value": filter_value, "limit": limit},
    }


def verify_with_independent_sql(result):
    """Recompute a parameterized Pandas result in DuckDB and compare counts.

    This checks numerical execution across implementations. It cannot prove the
    model chose the right parameters for the user's question.
    """
    from careinsight.read_only_sql import run_aggregate_sql

    operation = result["operation"]
    table = operation["table"]
    group_by = operation["group_by"]
    aggregation = operation["aggregation"]
    year = operation["year"]
    filter_column = operation["filter_column"]
    filter_value = operation["filter_value"]
    limit = operation["limit"]
    if table not in COLUMNS or group_by not in GROUP_COLUMNS:
        raise ValueError("Cannot cross-check unknown operation fields.")
    count = "COUNT(*)" if aggregation == "row_count" else "COUNT(DISTINCT PATIENT)"
    label = ("'All matching records'" if group_by == "none"
             else f"COALESCE(NULLIF({group_by}, ''), 'Unknown')")
    filters = []
    if year:
        filters.extend([
            f"CAST(START AS TIMESTAMPTZ) >= TIMESTAMPTZ '{year:04d}-01-01 00:00:00+00'",
            f"CAST(START AS TIMESTAMPTZ) < TIMESTAMPTZ '{year + 1:04d}-01-01 00:00:00+00'",
        ])
    if filter_column != "none":
        escaped = filter_value.replace("'", "''")
        filters.append(f"{filter_column} = '{escaped}'")
    sql = f"SELECT {label} AS group_name, {count} AS value FROM {table}"
    if filters:
        sql += " WHERE " + " AND ".join(filters)
    if group_by != "none":
        sql += " GROUP BY group_name ORDER BY value DESC, group_name ASC"
    sql += f" LIMIT {limit}"
    checked = run_aggregate_sql(sql, max_rows=limit)
    actual = [(row["group_name"], row["value"]) for row in result["rows"]]
    expected = [(row["group_name"], row["value"]) for row in checked["rows"]]
    if actual != expected:
        raise ValueError("Pandas and independent SQL counts do not agree.")
    return {"passed": True, "source_tables": checked["source_tables"],
            "checked_rows": len(expected)}
