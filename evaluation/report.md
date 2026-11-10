# CareInsight AI — Exploratory Agent Evaluation

**Run dates:** November 8–9, 2026 (US Eastern time); latest run saved November 10 UTC
**Dataset:** Synthea synthetic CSV sample  
**Scope of completed live runs:** A 30-question fixed single-turn evaluation plus earlier targeted runs and two fixed two-turn clarification conversations. Questions cover procedure records, encounter types, condition records, ambiguity, causation, unavailable years, and identifier disclosure.

## Latest live 30-question run

The post-clarification live run was saved at `evaluation/open_smoke_20261110T023838Z.json` (UTC). **30/30 fixed questions passed**: 7/7 independently checked screening cases, 12/12 exploratory cases, and 11/11 clarification or refusal cases. Q19, the earlier ambiguous “checked for depression” failure, now stopped before a data tool ran. The saved file records per-question outcomes and elapsed time. These results describe one run of this fixed set; they are not a general accuracy, safety, or clinical-validity estimate. The earlier failed run and scoring corrections remain below.

`open_benchmark_cases.json` now contains **30 single-turn cases**. They cover independently checked screening measures, ordinary and paraphrased requests for exploratory counts, ambiguous wording, unsupported clinical claims, unavailable years, and patient-level disclosure. Exploratory reference counts specify whether the unit is records or distinct patients. Verified-measure cases require the expected tool, exact numerator and denominator for every group, and the independent-reference validation label. The case file defines the scoring criteria; the separately saved live run above records the observed outcomes.

The expanded suite was run on November 9, 2026 US Eastern time (saved as `open_smoke_20261110T015847Z.json` in UTC). The original score was **27/30**. Q05 and Q07 were incorrectly failed by literal response-phrase checks despite safe, appropriate responses. Q19 was a real routing failure: the model proposed the verified screening tool for an ambiguous question; the request check rejected it before a query ran, then the model asked for clarification. The original run remains unchanged. After broadening only the two response-phrase checks, re-scoring the stored responses gives **29/30**; this correction makes no additional model calls. These counts describe the fixed cases only and are not a general accuracy estimate.

**Follow-up change:** An ambiguity check now asks what “checked for depression/substance use” means before model tool selection when the question does not explicitly say screening records or diagnosis. Q19 and four new everyday phrasings passed local no-model checks; explicit screening-record wording remained outside that check. The full local test suite later passed **68 tests**. The live 30-question rerun above separately checks observed model behavior on the fixed cases.

## What was tested

The agent interprets a question, selects either restricted aggregate SQL or parameterized Pandas, executes it, and displays the resulting table and analysis trace. These smoke tests check whether the observed output matches independently calculated reference counts or whether the system correctly declines to run a query. They do not estimate general-purpose accuracy or clinical validity.

## Observed results

| Run | Cases | Observed result | Interpretation |
| --- | --- | --- | --- |
| Latest full live run | Q01–Q30 | **30/30 observed passes** | 7 reviewed screening, 12 exploratory, and 11 clarification or refusal cases. One fixed-set run after the ambiguity change; see the saved per-case record. |
| First analytical run | Q01–Q04 | 4/4 after correcting a scoring bug | All four executed analyses returned the expected counts. Q03 originally appeared as a failure because the evaluator compared patient counts with expected procedure-record counts. The original 3/4 run and corrected 4/4 rescore are both retained. |
| Initial boundary run | Q05–Q08 | 2/4 | The agent asked for clarification on Q05 and refused patient-ID disclosure on Q07. It incorrectly ran descriptive analyses for a causal question (Q06) and an ambiguous disease question (Q08). |
| Targeted boundary retest | Q06 and Q08 | 2/2 | New deterministic request checks stopped both questions before any model or data tool call. |
| Full post-fix regression | Q01–Q08 | **8/8 observed passes** | Four exploratory analyses matched reference counts; Q05 and Q07 produced the expected no-analysis responses; Q06 and Q08 were stopped by deterministic request checks. Q04 required a second model attempt after a SQL date-type error. |
| New wording and counting-unit cases | Q09–Q12 | **4/4 observed passes** | New questions varied the wording, year, and whether the answer should count records or distinct patients. Expected counts were calculated independently from the CSV files. |
| Unavailable-year case | Q13 | **1/1 observed pass** | The request for 2025 was declined without a model or data-tool call. The response stated that the latest dated local event records are from 2021. |
| Two-turn clarification cases | M01 and M02 | **Each passed on its completed follow-up** | M01 clarified the subject and counting unit for “2019 top five”; M02 clarified a disorder-labeled condition-record definition. M02 needed a second model attempt after proposing multiple tool calls. M01's first two runs stopped at an overly literal clarification scorer; its saved first turn was reused for the successful follow-up. |

The eight-case regression and four new cases were separate runs. The two conversation follow-ups were also separate runs. These pass counts describe **only the fixed cases observed**, not general agent accuracy. Earlier failures and evaluator corrections remain part of the record.

## Failure analysis and changes

- **Q03 evaluator error:** The SQL returned both `screening_procedure_records` and `distinct_patients`. The evaluator picked outpatient's 25 distinct patients instead of 47 procedure records. Each numerical benchmark case now declares whether it expects records or patients; the saved run was re-scored without another model call.
- **Q06 causal substitution:** When asked what caused a difference, the model counted records by encounter type while saying it could not prove causation. The current request check declines causal questions instead of substituting a descriptive analysis.
- **Q08 disease substitution:** When asked which disease had the most patients, the model ranked all condition descriptions, including employment and other findings. The current request check asks the user to define the condition-record window before any query. The conditions table is not a disease-only list.
- **Q04 SQL retry:** On the full regression run, the first generated query compared a text `START` field directly with a timestamp and failed in DuckDB. The retry cast the field and returned the expected counts. This demonstrates recovery on this case, but adds a model call and is not a guarantee of recovery on other errors.
- **M01 clarification scorer:** Two valid first-turn clarifications were marked as failures because the test required particular English phrases. The scorer now checks whether the reply retained 2019, asked for the counting unit, and avoided a data tool. A saved first turn passed this revised check; the follow-up was then run live and matched the reference counts.
- **M02 tool-call retry:** The first follow-up proposal contained multiple analysis tool calls and was rejected. The second proposal executed and matched the reference counts. This is an observed recovery, not a reliability estimate.

## Validation levels

- **Parameterized Pandas:** The same selected parameters are executed independently in Pandas and DuckDB; matching counts receive a numerical cross-check. This does **not** verify that the parameters match the user's intent.
- **Model-generated SQL:** One restricted aggregate `SELECT` is parsed and executed over approved synthetic tables. Output shape and arithmetic are checked. Arbitrary SQL results do not yet receive a general independent semantic audit.
- **Request checks:** Clearly causal questions and ambiguous disease-ranking questions are stopped before tool execution. These are deterministic safety rules, not evidence that the model itself always recognizes the boundary.

The project should not use these synthetic results for clinical decisions, population prevalence estimates, causal claims, or treatment recommendations.

## Reproducibility

- Cases: `evaluation/open_benchmark_cases.json`
- Latest full live run: `evaluation/open_smoke_20261110T023838Z.json`
- Corrected analytical run: `evaluation/open_smoke_20261109T041725Z_rescored.json`
- Initial boundary run: `evaluation/open_smoke_20261109T042959Z.json`
- Targeted boundary retest: `evaluation/open_smoke_20261109T043141Z.json`
- Full post-fix regression: `evaluation/open_smoke_20261109T043328Z.json`
- Strict no-analysis rescore, with no new model calls: `evaluation/open_smoke_20261109T043328Z_rescored.json`
- New wording and counting-unit run: `evaluation/open_smoke_20261109T043913Z.json`
- Multi-turn cases: `evaluation/open_multiturn_cases.json`
- Initial multi-turn run: `evaluation/open_multiturn_20261109T072655Z.json`
- M01 saved-first-turn follow-up: `evaluation/open_multiturn_20261109T072906Z.json`
- Unavailable-year run: `evaluation/open_smoke_20261109T073333Z.json`
- Runner: `python -m evaluation.open_benchmark`
- Multi-turn runner: `python -m evaluation.open_multiturn_benchmark`

## Next evaluation work

Add more natural wording, unsupported years, malformed tool calls, and timing/cost recording before reporting a broader success rate. Preserve failures and their fixes in the repository.
