"""Resolve only the four approved local synthetic data tables."""

import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TABLES = {"patients", "encounters", "procedures", "conditions"}


def source_path(table: str) -> Path:
    if table not in TABLES:
        raise ValueError("This synthetic data table is not available.")
    raw = ROOT / "data" / "csv" / f"{table}.csv"
    demo = ROOT / "data" / "demo" / f"{table}.csv.gz"
    if os.getenv("CAREINSIGHT_USE_DEMO_DATA") == "1":
        if demo.is_file():
            return demo
        raise FileNotFoundError("Packaged demo data is missing: " + table)
    if raw.is_file():
        return raw
    if demo.is_file():
        return demo
    raise FileNotFoundError(
        "No Synthea CSV data found. Add data/demo or download the source CSVs."
    )
