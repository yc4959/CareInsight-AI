# Substance Use Screening Record Coverage — Demonstration Metric

## Data source
Synthea synthetic patient CSV data.

## Measurement period
2020-01-01 inclusive to 2021-01-01 exclusive, UTC.

## Denominator
Unique patients who:
- Were at least 18 years old on 2020-01-01;
- Had no recorded death date, or a death date after 2020-12-31;
- Had at least one encounter starting during the measurement period.

All encounter types are included. A missing death date means no death was recorded.

## Numerator
Denominator patients with at least one procedure starting during the
measurement period with code `713106006`, described in this dataset as
"Screening for drug abuse (procedure)". Count each patient once.

## Calculation
Record coverage = numerator / denominator.

## Interpretation
This is a custom demonstration metric, not an official quality measure.
It measures the presence of a qualifying procedure record, not whether
screening was performed or whether a patient has a substance use disorder.
The data are synthetic and cannot establish real-world population patterns,
causes, or intervention effects.
