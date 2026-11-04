# CareInsight AI

CareInsight AI is a population health analytics prototype for plain-English questions about recorded depression screenings in synthetic patient data.

## What it does

- Calculates a custom 2020 screening record coverage measure.
- Compares results overall, by age group, or by the dataset's original GENDER field.
- Asks a short clarification when the requested measure is unclear.
- Uses an AI model to interpret questions and select a controlled analysis tool. Python and SQL calculate results.
- Displays a dashboard, chart, report, and supporting evidence.

## Data and interpretation

The source is Synthea's publicly available **1K sample CSV dataset**: https://synthetichealth.github.io/downloads.html

Download the CSV sample under Previous Versions (2019–2021), extract it, and place the CSV files in `data/csv/`.

The original CSV files are excluded from this repository. The data are synthetic, and the measure is a custom demonstration metric rather than an official quality measure. A missing screening record does not prove screening was not performed. Observed group differences do not establish causes or statistical significance.

See `docs/metric_definition.md` for the numerator, denominator, time window, and procedure codes.

## Run locally

Requires Python 3.11 or later. In the project directory, run these commands in order:

1. `python3 -m venv .venv`
2. `source .venv/bin/activate`
3. `python -m pip install -r requirements.txt`
4. `python -m streamlit run app.py`

The dashboard and charts use local data. To use **Ask CareInsight**, configure `DEEPSEEK_API_KEY`, `DEEPSEEK_BASE_URL`, and `DEEPSEEK_MODEL` in the server's environment. Never commit an API key. The dashboard can run without one; the question-answering section will say the key is missing.

## Verify

Run `python -m pytest tests/test_summary_tool.py -q`.

The fixed-data tests check known totals, group reconciliation, comparisons, and invalid parameters.

## Current scope

The first version supports 2020 adult depression screening record coverage, overall or grouped by age or GENDER. It does not analyze diagnoses, other screening measures, custom population filters, or other years.

`evaluation/benchmark_questions.json` contains fixed questions. `evaluation/manual_checks.md` records observed successes and failures. No overall reliability or impact claim has been established.
