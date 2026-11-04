# Depression Screening Record Coverage — Demo Metric

## Purpose
Measure documented depression screening coverage among eligible
synthetic adult patients with an encounter during 2020.

## Data source
Synthea synthetic patient CSV files.
This is a custom demonstration metric, not an official quality measure.

## Measurement period
2020-01-01 00:00:00 UTC inclusive through
2021-01-01 00:00:00 UTC exclusive.

## Denominator
Unique patients who:
- Were at least 18 years old on 2020-01-01.
- Had no recorded death date, or died after 2020-12-31.
- Had at least one encounter starting within the measurement period.

All encounter types are currently included.
A missing death date is treated as no recorded death.

## Numerator
Denominator patients with at least one procedure starting within
the measurement period with one of these codes:

- 171207006: General depression screening.
- 454711000124102: PHQ-2 depression screening.
- 715252007: PHQ-9 depression screening.

Codes were selected from descriptions in the supplied dataset.
Each patient is counted once, regardless of procedure count.

## Calculation
Coverage = numerator / denominator.
If the denominator is zero, coverage is undefined.

## Age groups
Age is measured on 2020-01-01.
Groups: 18–39, 40–64, and 65+.

## Validated baseline
- Denominator: 699
- Numerator: 545
- Without a qualifying screening record: 154
- Coverage: 77.97%
- SQL and independent Pandas counts agree.

## Interpretation limits
- Missing screening documentation does not prove screening was not done.
- Synthetic data findings do not establish real-world population patterns.
- Group differences do not establish causes or intervention effects.
- This metric does not evaluate screening results or follow-up quality.
- Baseline values are validation references, not hardcoded tool answers.
