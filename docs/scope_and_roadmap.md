# CareInsight AI: supported scope and full product vision

## What the live app can do

The hosted app packages **all rows**, but only the approved analysis columns, from four tables in Synthea's public 1K sample: `patients`, `encounters`, `procedures`, and `conditions`. The files are compressed to roughly 4.3 MB. Names, addresses, and other unused source columns are not packaged. Synthetic patient and encounter IDs remain internally for joins; individual identifiers are not available as query results.

The agent accepts natural-language descriptive questions, asks for clarification when a counting unit or subject is unclear, and selects a reviewed screening tool, restricted aggregate SQL, or parameterized Pandas. It displays the executed query or parameters and the checks performed.

| Question type | Current answer and evidence |
| --- | --- |
| Adult depression or substance-use screening **record coverage** in full calendar year 2019 or 2020, overall, by age group, or by original `GENDER` | Reviewed cohort and procedure-code definition. SQL group counts must equal an independent Pandas calculation. |
| The same screening measure compared between 2019 and 2020 | Each year's separate adult cohort and counts are independently checked. This is a comparison of annual records, not the same people followed over time. |
| Other aggregate questions over approved fields, such as procedure descriptions, encounter types, or condition records in a selected year | Exploratory result. Query restrictions and numeric checks apply; a Pandas result also receives an independent SQL count check. The meaning of an arbitrary question and its chosen measure are not independently established. |

The underlying event records span many decades and stop in November 2021. Historical records being present does **not** make every year complete, equally generated, or suitable for a comparable annual screening measure. The current reviewed annual coverage window is 2019–2020. A missing procedure record does not prove a screening was not performed. Condition records are not disease prevalence, and these synthetic results cannot establish real-world rates, causes, or treatment effects.

The [annual data audit](annual_data_audit.md) summarizes 2000–2021 record availability and highlights an abrupt procedure-volume change around 2011–2012. It is an availability check, not approval to compare screening coverage across all those years.

## What a fuller product could support

1. Add selected fields and tables from the other Synthea CSVs when a concrete question needs them, such as medication, observation, immunization, or payer records. Define joins, date semantics, missingness rules, and safe output shapes for each table before exposing it to the agent.
2. Extend reviewed measures to other years only after checking year completeness, code availability, cohort comparability, and independent reference calculations. Preserve the distinction between record counts, unique patients, coverage denominators, and outcomes.
3. Add repeat-record, encounter-linked, and longitudinal questions with separately defined cohorts and validation rules. Add uncertainty or models only when the data and estimand support them; synthetic convenience data are not a probability sample of a target population.
4. Expand the evaluation set for plain-language, ambiguous, unsupported, and adversarial questions. Record tool choice, query, validation outcome, failures, latency, and cost. Present results as observed tests, not as unmeasured accuracy claims.
5. Consider scalable storage and execution for a larger hosted version, plus access control and monitoring if the product ever moves beyond public synthetic demonstration data.

These are **planned directions**, not capabilities of the current live demo. The goal is broader question coverage with explicit definitions and evidence levels, rather than accepting any question and treating an executable query as a verified answer.

## Why the complete download is not in the free hosted demo

The local source folder contains **18 CSV files, about 539 MB uncompressed**; `claims_transactions.csv` is about 296 MB. The public GitHub repository currently excludes `data/csv/` and includes only the four compressed approved-column files needed by the app. GitHub enforces a 100 MB limit on an ordinary single repository object and recommends storing generated large files outside Git. This is a GitHub repository limit, not a limit on how many historical years may be analyzed.

Streamlit Community Cloud has finite CPU and memory; its published approximate memory range is 690 MB–2.7 GB, and those limits may change. Loading large CSVs into Pandas and DuckDB can use substantially more memory than their on-disk size. Community Cloud also sleeps apps after 12 hours without traffic. These limits make a 539 MB raw checkout and eager in-memory loading a poor default for this portfolio demo. They do not prevent a larger version using selective columns, Parquet or database storage, and demand-based queries.

Sources: [Synthea downloads](https://synthetichealth.github.io/downloads.html), [GitHub repository limits](https://docs.github.com/en/repositories/creating-and-managing-repositories/repository-limits), [Streamlit Community Cloud resources and hibernation](https://docs.streamlit.io/deploy/streamlit-community-cloud/manage-your-app).
