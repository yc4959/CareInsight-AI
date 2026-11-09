"""Restricted aggregate SQL execution over selected Synthea CSV columns.

This is a local V2 prototype. It is not yet a public, multi-user SQL sandbox.
"""

from functools import lru_cache
from pathlib import Path

import duckdb
import pandas as pd
import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

from careinsight.data_source import source_path


ROOT = Path(__file__).resolve().parents[1]
ALLOWED_COLUMNS = {
    "patients": ("Id", "BIRTHDATE", "DEATHDATE", "GENDER"),
    "encounters": ("Id", "START", "PATIENT", "ENCOUNTERCLASS"),
    "procedures": ("START", "PATIENT", "ENCOUNTER", "CODE", "DESCRIPTION"),
    "conditions": ("START", "STOP", "PATIENT", "ENCOUNTER", "CODE", "DESCRIPTION"),
}
IDENTIFIER_COLUMNS = {"id", "patient", "encounter"}


@lru_cache(maxsize=1)
def _tables():
    return {
        name: pd.read_csv(
            source_path(name), usecols=columns, dtype="string"
        )
        for name, columns in ALLOWED_COLUMNS.items()
    }


def _identifier_outside_aggregate(projection):
    for column in projection.find_all(exp.Column):
        if column.name.lower() not in IDENTIFIER_COLUMNS:
            continue
        parent = column.parent
        while parent is not None and parent is not projection.parent:
            if isinstance(parent, exp.AggFunc):
                # COUNT can disclose only a count. MIN, MAX, LIST and similar
                # aggregates could return an underlying patient identifier.
                return not isinstance(parent, exp.Count)
            parent = parent.parent
        else:
            return True
    return False


def validate_sql(sql: str) -> tuple[str, list[str]]:
    """Accept one aggregate SELECT over the exposed tables."""
    if not isinstance(sql, str) or not sql.strip() or len(sql) > 10_000:
        raise ValueError("Provide a nonempty SQL query under 10,000 characters.")
    try:
        statements = sqlglot.parse(sql, read="duckdb")
    except ParseError as exc:
        raise ValueError("SQL could not be parsed.") from exc
    if len(statements) != 1 or not isinstance(statements[0], exp.Select):
        raise ValueError("Exactly one SELECT statement is allowed.")

    tree = statements[0]
    cte_names = {cte.alias_or_name.lower() for cte in tree.find_all(exp.CTE)}
    source_tables = set()
    for table in tree.find_all(exp.Table):
        name = table.name.lower()
        if table.db or table.catalog or not name:
            raise ValueError("Qualified tables and table functions are not allowed.")
        if name in cte_names:
            continue
        if name not in ALLOWED_COLUMNS:
            raise ValueError(f"Table is not available: {name}")
        source_tables.add(name)
    if not source_tables:
        raise ValueError("Query must use an available data table.")
    if not any(isinstance(node, exp.AggFunc) for node in tree.walk()):
        raise ValueError("Only aggregate analysis is available.")
    if any(isinstance(item, exp.Star) for item in tree.expressions):
        raise ValueError("SELECT * is not allowed in the final output.")
    if any(_identifier_outside_aggregate(item) for item in tree.expressions):
        raise ValueError("Patient and encounter identifiers cannot be output.")

    return tree.sql(dialect="duckdb"), sorted(source_tables)


def run_aggregate_sql(sql: str, max_rows: int = 200) -> dict:
    """Run validated SQL with filesystem access disabled and a result cap."""
    if type(max_rows) is not int or not 1 <= max_rows <= 500:
        raise ValueError("max_rows must be an integer between 1 and 500.")
    normalized_sql, source_tables = validate_sql(sql)
    connection = duckdb.connect(config={
        "enable_external_access": "false",
        "memory_limit": "512MB",
        "threads": "2",
    })
    try:
        for name, frame in _tables().items():
            connection.register(name, frame)
        capped_query = (
            f"SELECT * FROM ({normalized_sql}) AS careinsight_result "
            f"LIMIT {max_rows + 1}"
        )
        cursor = connection.execute(capped_query)
        columns = [column[0] for column in cursor.description]
        values = cursor.fetchall()
        if len(values) > max_rows:
            raise ValueError("Query returned too many rows.")
        rows = [dict(zip(columns, row)) for row in values]
        return {
            "sql": normalized_sql,
            "source_tables": source_tables,
            "row_count": len(rows),
            "rows": rows,
        }
    finally:
        connection.close()
