# Annual data audit: 2000–2021

Source: the four packaged, approved-column tables from the public Synthea 1K sample. Run `CAREINSIGHT_USE_DEMO_DATA=1 python -m scripts.audit_years` to regenerate this report. The three event tables retain all source rows; this report selects START years 2000–2021.

| Year | Encounters | Encounter months | Procedures | Procedure months | Conditions | Condition months | Depression code rows | Substance-use code rows |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2000 | 787 | 12 | 485 | 12 | 521 | 12 | 78 | 11 |
| 2001 | 800 | 12 | 526 | 12 | 544 | 12 | 90 | 14 |
| 2002 | 807 | 12 | 524 | 12 | 537 | 12 | 104 | 12 |
| 2003 | 837 | 12 | 613 | 12 | 544 | 12 | 95 | 20 |
| 2004 | 916 | 12 | 621 | 12 | 603 | 12 | 110 | 12 |
| 2005 | 863 | 12 | 479 | 12 | 573 | 12 | 79 | 15 |
| 2006 | 1026 | 12 | 600 | 12 | 620 | 12 | 120 | 27 |
| 2007 | 909 | 12 | 522 | 12 | 608 | 12 | 91 | 16 |
| 2008 | 1017 | 12 | 581 | 12 | 683 | 12 | 116 | 20 |
| 2009 | 927 | 12 | 426 | 12 | 673 | 12 | 99 | 17 |
| 2010 | 1014 | 12 | 462 | 12 | 748 | 12 | 81 | 17 |
| 2011 | 1486 | 12 | 1117 | 12 | 1166 | 12 | 227 | 46 |
| 2012 | 2897 | 12 | 5905 | 12 | 1477 | 12 | 1236 | 192 |
| 2013 | 2817 | 12 | 6353 | 12 | 1437 | 12 | 1211 | 204 |
| 2014 | 4650 | 12 | 7957 | 12 | 1954 | 12 | 1404 | 225 |
| 2015 | 3070 | 12 | 6636 | 12 | 1549 | 12 | 1313 | 211 |
| 2016 | 3034 | 12 | 6953 | 12 | 1505 | 12 | 1334 | 212 |
| 2017 | 2972 | 12 | 6683 | 12 | 1617 | 12 | 1385 | 228 |
| 2018 | 3071 | 12 | 6970 | 12 | 1700 | 12 | 1426 | 237 |
| 2019 | 3154 | 12 | 7229 | 12 | 1668 | 12 | 1433 | 255 |
| 2020 | 3264 | 12 | 7520 | 12 | 2054 | 12 | 1496 | 268 |
| 2021 | 4225 | 11 | 6928 | 11 | 1805 | 11 | 1317 | 229 |

`months` is the number of distinct calendar months containing at least one row. Twelve months of records do not establish complete observation or comparable data generation. Code counts are raw procedure rows, not unique patients or screening completion rates.

## Data quality and interpretation

- `encounters`: 0 invalid START dates; 0 missing PATIENT values; latest START 2021-11-19.
- `procedures`: 0 invalid START dates; 0 missing PATIENT values; latest START 2021-11-19.
- `conditions`: 0 invalid START dates; 0 missing PATIENT values; latest START 2021-11-15.
- 2021 has records in January–November only, so this sample cannot support a complete-calendar-year 2021 comparison.
- Procedure volume rises sharply between 2010 and 2012 (462 to 5,905 rows). Screening-code rows rise too. The audit does not establish why this happened; it is a warning against treating the full series as a uniform clinical trend.
- The current independently checked adult screening measures remain limited to 2019 and 2020. Extending them to another year requires year-specific cohort, code, missingness, and independent count checks.
- These are synthetic records, not estimates of real population screening, diagnosis, or treatment.
