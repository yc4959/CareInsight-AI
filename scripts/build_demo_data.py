"""Build a compact, attributed demo copy from the downloaded Synthea CSVs."""

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
COLUMNS = {
    "patients": ["Id", "BIRTHDATE", "DEATHDATE", "GENDER"],
    "encounters": ["Id", "START", "PATIENT", "ENCOUNTERCLASS"],
    "procedures": ["START", "PATIENT", "ENCOUNTER", "CODE", "DESCRIPTION"],
    "conditions": ["START", "STOP", "PATIENT", "ENCOUNTER", "CODE", "DESCRIPTION"],
}


def _sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", type=Path, default=ROOT / "data" / "csv")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "data" / "demo")
    args = parser.parse_args()
    raw, dest = args.source_dir, args.output_dir
    missing = [name for name in COLUMNS if not (raw / f"{name}.csv").is_file()]
    if missing:
        raise SystemExit("Missing source CSVs: " + ", ".join(missing))
    dest.mkdir(parents=True, exist_ok=True)
    manifest = {
        "source": "Synthea 1K sample CSV, Previous Versions (2019–2021)",
        "source_url": "https://synthetichealth.github.io/downloads.html",
        "transformation": "Selected approved columns only; row values and row order preserved; gzip compressed.",
        "tables": {},
    }
    for name, columns in COLUMNS.items():
        source = raw / f"{name}.csv"
        frame = pd.read_csv(source, dtype="string", usecols=columns)
        output = dest / f"{name}.csv.gz"
        frame.to_csv(output, index=False,
                     compression={"method": "gzip", "compresslevel": 9, "mtime": 0})
        manifest["tables"][name] = {
            "rows": len(frame), "columns": list(frame.columns),
            "source_sha256": _sha256(source),
            "demo_sha256": _sha256(output),
        }
        print(f"{name}: {len(frame):,} rows, {output.stat().st_size:,} compressed bytes")
    (dest / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    )
    print("Demo data and manifest saved in data/demo/.")


if __name__ == "__main__":
    main()
