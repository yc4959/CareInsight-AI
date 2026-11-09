# CareInsight AI

**A natural-language analytics prototype for synthetic healthcare records.** Ask a plain-English data question; the model selects a reviewed screening measure, restricted SQL, or parameterized Pandas. One app displays the calculated table, chart when suitable, plan, evidence level, and analysis trace.

This is a local portfolio prototype. It uses **Synthea synthetic data**, not real patient records. Its exploratory answers are not clinical findings or validated population estimates.

## Try it

- “Which procedure descriptions appeared most often in 2020? Show the top 10 by number of records.”
- “In 2019, which procedure codes involved the most different patients? Show the top five codes.”
- “Which encounter types have the most substance use screening procedure records in 2020?”
- “2019 top five” is deliberately incomplete; the agent should clarify what to rank.
- “What were people getting checked for most often in 2020?” tested clarification about the type of record and whether to count records or people.

The app accepts open-text descriptive questions over the exposed data. It cannot answer every healthcare question. It should clarify ambiguous requests and decline unsupported causal, clinical, or patient-level requests.

## What happens after a question

1. The model interprets the request and selects a reviewed screening tool, **restricted aggregate SQL**, or **parameterized Pandas**.
2. For a reviewed 2020 screening measure, code builds SQL from the selected measure and grouping, then compares every count with an independent Pandas reference. Other generated SQL receives structural and arithmetic checks.
3. Pandas aggregations are recomputed in DuckDB using the same selected parameters. This checks the numbers, **not** whether the selected parameters match the user's intent.
4. The app shows a table, chart when suitable, source tables, tool parameters or SQL, and checks performed.

The exploratory tool uses `patients`, `encounters`, `procedures`, and `conditions`. Source columns are restricted in code. A query may count records or distinct patients; these are different measures. Condition descriptions include findings and social factors, so condition-record counts must not be presented as disease prevalence.

## One main app, two evidence levels

| Result shown in `app.py` | Purpose | Evidence level |
| --- | --- | --- |
| Independently checked screening result | A defined 2020 adult depression or substance-use screening record measure, overall or by age group or GENDER. | SQL counts must match the independent reference for every group before publication. The model's choice of measure and grouping is checked against the question. |
| Exploratory result | Other descriptive questions over approved synthetic tables, including procedure and encounter counts. | Query restrictions and result checks. Pandas counts also receive a cross-tool numerical check; arbitrary SQL meanings are not independently audited. |

Earlier interfaces are retained under `legacy/` for project history; `app.py` is the single main entry point.

The 2020 adult screening measures are **custom demonstration measures**, not official quality metrics. Their denominator, code lists, and time windows are documented in `docs/metric_definition.md` and `docs/substance_use_screening_metric.md`.

## Data and local setup

The repository includes four small gzip CSV files under `data/demo/`. They are a column subset of Synthea's public **1K sample CSV** under Previous Versions (2019–2021) on the [Synthea downloads page](https://synthetichealth.github.io/downloads.html). They contain synthetic records and no names or addresses. See `data/demo/README.md` for provenance and citation, and `data/demo/manifest.json` for row counts and file hashes. The packaged event files contain records through 2021; this does not make every historical year or partial year comparable.

The app uses the packaged data automatically. To regenerate them from the original download, extract the CSVs into `data/csv/` and run `python scripts/build_demo_data.py`. Original CSVs are excluded from Git. Set `CAREINSIGHT_USE_DEMO_DATA=1` to force the packaged copy when both are present. Patient and encounter IDs remain in the packaged files to support joins; the app restricts queries from returning individual identifiers.

Requires Python 3.11 or later. From the project directory:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

The main app requires `DEEPSEEK_API_KEY`, `DEEPSEEK_BASE_URL`, and `DEEPSEEK_MODEL` in the server environment. Keep keys out of source files and Git. A hosted version needs these values configured as server secrets so visitors do not supply their own key. A live hosted demo has not yet been verified.

## Deploy on Streamlit Community Cloud

After the project is published to GitHub, create a Community Cloud app using `app.py` as the entry point. Select Python 3.11 in Advanced settings to match the tested local environment. The repository's `requirements.txt` supplies Python dependencies and `data/demo/` supplies the synthetic demonstration data; the 539 MB original CSV download is not needed on the server.

Add these three **root-level** values in Community Cloud's Secrets settings, using the provider values that worked locally:

```toml
DEEPSEEK_API_KEY = "your-private-key"
DEEPSEEK_BASE_URL = "your-provider-base-url"
DEEPSEEK_MODEL = "your-model-id"
```

Do not commit a populated `secrets.toml` file. The app reads these values from environment variables; Streamlit exposes root-level secrets that way. The server owner pays for model calls. Verify both a reviewed screening question and an exploratory question on the hosted URL before sharing it as a live demo.

## Evaluation

`evaluation/report.md` records the observed runs and failures. On fixed questions, the post-fix eight-case regression passed **8/8**, four additional wording and counting-unit cases passed **4/4**, and the unavailable-year case passed **1/1**. Two separate clarification follow-ups each passed after the requested definition was supplied. These are **small observed test runs**, not an overall accuracy estimate. Earlier failures and evaluator corrections remain in the report.

Run local checks with:

```bash
python -m pytest tests -q
CAREINSIGHT_USE_DEMO_DATA=1 python -m pytest tests -q
python -m evaluation.open_benchmark --limit 8
python -m evaluation.open_multiturn_benchmark
```

The two benchmark commands call the configured model and consume API usage. The test suite checks code behavior locally. Do not quote a new pass rate until the new run has actually completed.

## Interpretation limits

- Missing screening documentation does not prove a screening was not performed.
- Counts from synthetic patients do not describe a real population.
- Descriptive differences do not establish statistical significance, causes, or intervention effects.
- A passed numerical cross-check does not prove that a free-form question was interpreted correctly.
- The SQL restrictions are for a local prototype; this is not a reviewed multi-user clinical data service.

The next portfolio milestones are broader question evaluation, a short walkthrough video, and a verified hosted demo with server-managed model credentials.
