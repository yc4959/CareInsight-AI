# Manual Evaluation Notes

## Scope
Synthea synthetic data; custom 2020 adult depression screening
record coverage metric.

## Observed checks
| Scenario | Observed result |
|---|---|
| Explicit GENDER screening comparison | Selected the summary tool with group_by=gender; reported F=301/388 and M=244/311 correctly. |
| Ambiguous depression question | A clarification question appeared in the successful web test. |
| Clarified as screening record coverage | Continued with the requested GENDER screening analysis. |
| Clarified as depression diagnoses | Displayed that no analysis was run; did not display a screening report. |
| Explicit unsupported year 2021 | CLI year guard stopped the request before model execution. |

## Analysis tests
The local pytest suite passed 10 checks covering fixed-data
baselines, group reconciliation, comparisons, and invalid parameters.

## Known issues and limitations
- Earlier clarification attempts did not consistently trigger the
  clarification tool. One successful run does not establish reliability.
- Reports previously speculated about undocumented screening.
- A report incorrectly generalized zero missing GENDER values to
  completeness of categories.
- Reports sometimes expose internal field names.
- The explicit-year guard does not fully interpret relative years,
  negation, or complex requests.
- Automated report factuality validation is not implemented.
- Web outcomes were manually observed, not collected by an automated
  benchmark runner.
- No overall task success rate or efficiency improvement is claimed.

## Next evaluation work
Create a fixed benchmark with expected tool choices, parameters,
clarification behavior, refusals, and numerical results.
Record failures as well as successes.
