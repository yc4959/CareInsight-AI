# Annual screening records (2018–2020)

The app provides independently checked single-year results for 2018, 2019, and 2020. Its reviewed cross-year comparison currently covers **2019–2020 only**. This is a custom demonstration analysis, not an official quality measure or an estimate for a real population.

## Annual definition

For year `Y`, the observation window is UTC `[Y-01-01, (Y+1)-01-01)`. The denominator contains unique patients who were at least 18 on January 1 of `Y`, have no recorded death through December 31 of `Y`, and have at least one encounter starting during that window. All encounter types are included. Missing death dates mean no death was recorded; they do not verify survival.

The numerator contains denominator patients with at least one procedure starting in the same window with the selected screening code. Depression codes are `171207006`, `454711000124102`, and `715252007`. The substance-use demonstration code is `713106006`. Each patient counts once per year. These are records of procedures, not verified clinical completion or screening results.

Each year's cohort is constructed separately. A patient may appear in more than one year, one year, or neither. A change in annual coverage does not represent the same patients followed over time and does not establish cause, statistical significance, or a real-world trend. No confidence interval is reported because this synthetic convenience dataset is not a probability sample of a target population.

## Verification

The reviewed SQL template and an independent Pandas implementation both calculate the numerator and denominator for each year. The app publishes a reviewed annual result only after every group count matches. The reference counts are calculated from the files at runtime; they are not substituted as answers.

For the packaged demo data, the observed overall references are:

| Year | Eligible adults | Depression record | Substance-use record |
| --- | ---: | ---: | ---: |
| 2018 | 672 | 497 | 212 |
| 2019 | 674 | 510 | 219 |
| 2020 | 699 | 545 | 230 |

The event files have records only through November 2021. The app can explore 2021 records, but it does not label a 2021 full-year screening comparison as reviewed or compare it with the complete years.
