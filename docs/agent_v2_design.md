# CareInsight AI — Agent V2 Design Draft

## Product goal

A nontechnical user asks a healthcare analytics question in plain English. The
agent plans an analysis, queries permitted synthetic patient data, selects a
calculation and chart, checks the evidence, and explains the result. Questions
are freely phrased within the documented dataset and analysis boundaries.

The existing 2020 depression and substance use screening measures are the
validated reference cases. The benchmark questions test behavior; they are not
answers stored for retrieval.

## Workflow

1. **Interpret:** Identify the requested population, measure, period,
   grouping, and output. Ask a short clarification when one is ambiguous.
2. **Plan:** Produce a structured plan that names permitted source tables,
   join keys, code definitions, denominator, numerator, aggregation, and chart.
   Show the plan in the execution record.
3. **Query:** Generate SQL from the plan and execute it against a restricted,
   read-only DuckDB environment. Allow only approved tables and columns.
   Reject file access, mutations, unsupported functions, and unbounded output.
4. **Analyze:** Use Python tools for allowed calculations on returned tabular
   data: counts, rates, group differences, missingness, and reconciliation.
   Do not execute unrestricted model-written Python in the public app.
5. **Validate:** Check query scope, row counts, unique-patient rules,
   numerator <= denominator, group totals, missing values, and formulae.
   For validated measures, compare against independent reference results.
   Stop or mark exploratory analyses when independent validation is absent.
6. **Visualize:** Generate a Plotly chart from the validated result table and
   a constrained chart specification; show denominators with percentages.
7. **Report:** Answer the question in plain English with counts, period,
   source, SQL/plan trace, caveats, and a clearly labeled follow-up audit idea
   where appropriate. Do not claim clinical, causal, or population findings.

## First end-to-end example

Question: “Compare recorded substance use screenings between men and women in
2020.”

The agent should identify the adult cohort and source procedure code 713106006,
join patients, encounters, and procedures, generate a grouped SQL query, and
calculate F 113/388 (29.12%) and M 117/311 (37.62%). It should show a bar
chart and explain that these are synthetic screening *records*, not diagnoses
or proof that screening occurred. The output should agree with the existing
independently verified tool.

## First implementation boundary

- Data: local Synthea CSV files, starting with patients, encounters, procedures.
- Period: 2020 only until another year is independently validated.
- Core measures: two existing screening record measures. Other proposed
  measures require a reviewed definition before they become validated outputs.
- Groupings: overall, age group, original GENDER field. Additional grouping
  fields require data-quality checks and small-group handling.
- User interface: keep the current dashboard and question box. Add an analysis
  trace that shows plan, SQL, validation checks, and chart source data.
- Current deterministic tool remains available as a reference and fallback
  while the new query path is evaluated.

## Evidence and acceptance

The first V2 query path is ready for expansion only when it reproduces the
verified overall, age, and GENDER results for both measures; rejects unsafe
or unsupported queries; and passes a fixed question set including ambiguous,
out-of-scope, and multi-turn cases. Report actual pass counts by category and
retain failed examples. A successful SQL execution alone is not validation of
the intended metric.
