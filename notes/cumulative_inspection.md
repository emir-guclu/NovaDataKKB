# BDDK Cumulative Series Manual Inspection

## Purpose

Before implementing automatic de-cumulation, selected real BDDK series were manually inspected
for within-year monotonicity and year-start reset behavior.

## 1. BDDK Weekly — Krediler / Toplam Krediler / TOPLAM

Classification: `none`

Observed values include both increases and decreases within the same year.

Examples:
- 2021-01-08: 3,544,778.64
- 2021-01-15: 3,553,726.00
- 2021-01-22: 3,549,534.91
- 2021-02-05: 3,501,920.43

Year boundaries also show no reset:
- 2021 last: 4,899,579.24
- 2022 first: 4,962,803.15
- 2022 last: 7,568,340.01
- 2023 first: 7,573,416.82

Conclusion:
This behaves as a stock/outstanding balance series rather than a cumulative flow.
Do not de-cumulate.

## 2. BDDK Weekly — Mevduat / Mevduat (Katılım Fonu) / TOPLAM

Classification: `none`

The series rises and falls within each year.

Examples:
- 2021-01-08: 3,429,567.08
- 2021-01-15: 3,461,450.03
- 2021-01-22: 3,452,896.08
- 2021-02-05: 3,334,933.52

There is no year-start reset:
- 2021 last: 5,303,494.70
- 2022 first: 5,421,849.12
- 2022 last: 8,865,710.59
- 2023 first: 8,858,988.08

Conclusion:
This is a stock series. Do not de-cumulate.

## 3. BDDK Monthly — Bilanço / Nakit Değerler / TP

Classification: `none`

Examples:
- 2021-01: 16,313.305
- 2021-02: 16,268.733
- 2021-03: 17,161.216
- 2021-05: 18,374.993
- 2021-06: 17,188.794

The values fluctuate and do not reset at the beginning of the year.

Conclusion:
This is a balance-sheet stock series. Do not de-cumulate.

## 4. BDDK Monthly — Kar Zarar / Kredilerden Alınan Faizler (Kar Payları) / TP

Classification: `ytd`

The series increases throughout each year and resets strongly in January.

2021:
- Jan: 25,382.899
- Feb: 49,154.549
- Mar: 77,130.808
- Dec: 365,098.455

2022:
- Jan: 39,274.998
- Feb: 76,416.459
- Mar: 120,863.759
- Dec: 667,201.379

2023:
- Jan: 71,737.604
- Dec: 1,341,146.608

Observed year-end/year-start reset:
- 2021 Dec: 365,098.455 -> 2022 Jan: 39,274.998
- 2022 Dec: 667,201.379 -> 2023 Jan: 71,737.604

Expected periodic values for a YTD de-cumulation:
- 2021 Jan = 25,382.899
- 2021 Feb = 49,154.549 - 25,382.899 = 23,771.650
- 2021 Mar = 77,130.808 - 49,154.549 = 27,976.259
- 2022 Jan = 39,274.998

Conclusion:
This is a year-to-date cumulative flow series and must be de-cumulated within each calendar year.

## 5. BDDK Monthly — Krediler / İskontolu İşlemlerden Alacaklar / Kısa TP

Classification: `none`

Although the long-term direction is upward, values can decrease within a year and there is no
January reset.

Examples:
- 2021-04: 26,775.753
- 2021-05: 25,621.171
- 2021-06: 25,608.141
- 2021-07: 23,932.124

Year boundary:
- 2021 Dec: 30,987.436
- 2022 Jan: 32,211.484

Conclusion:
This is a stock series. Growth over time alone must not be treated as evidence of cumulative behavior.

## 6. Additional Kar Zarar Inspection

Additional income-statement series were inspected to avoid assuming that every row in the
Kar Zarar table follows the same accumulation rule.

### Clear YTD examples

#### Aktiflerimizin Satışından Elde Edilen Gelirler / TP

Classification: `ytd`

2021:
- Jan: 193.292
- Dec: 5,239.442
- within-year decreases: 0

2022:
- Jan: 426.332
- Dec: 9,228.485
- within-year decreases: 0

The strong December-to-January reset and accumulation during the year support YTD classification.

#### Toplam Faiz (Kar Payı) Gelirleri / Toplam

Classification: `ytd`

- 2021 Jan: 40,913.287
- 2021 Dec: 641,491.556
- 2022 Jan: 70,773.294
- 2022 Dec: 1,403,203.256
- 2023 Jan: 133,265.235

All inspected years have zero within-year decreases and clear January resets.

#### Ters Repo İşlemlerinden Alınan Faizler

TP, YP and Toplam variants show the same YTD pattern.

Example, Toplam:
- 2021 Jan: 281.042
- 2021 Dec: 3,657.182
- 2022 Jan: 443.859
- 2022 Dec: 4,675.086

Classification: `ytd`

### Ambiguous / Manual Review Required

#### Toplam Diğer Faiz Dışı (Kar Payı Dışındaki) Gelirler (Giderler)

TP, YP and Toplam variants contain many intra-year decreases and both positive and negative
values.

Examples:
- TP 2021 within-year decreases: 6
- Toplam 2021 within-year decreases: 8
- YP 2021 within-year decreases: 6

These may represent net cumulative income/expense flows where negative period contributions can
cause a cumulative value to fall. However, the observed data alone does not safely satisfy the
simple monotonic-YTD rule.

Conclusion:
Do not automatically classify these series as `ytd` or apply de-cumulation until their source
definition/accounting semantics are manually confirmed.

## Final cumulative review

A conservative candidate scan was run across BDDK Monthly series.

Initial manual review had identified 7 YTD series. A broader year-boundary
audit of the `Kar Zarar` category found 39 additional monetary flow series
with strong annual reset evidence (`reset_ratio >= 0.80`).

Final reviewed classification:

- 46 Monthly `Kar Zarar` series: `accumulation = ytd`
- Raw YTD observations are retained.
- Each reviewed YTD series has a derived `_periodic` counterpart.
- No series was automatically reclassified based only on monotonicity.
- Remaining flagged candidates are primarily ratios, balances, capital,
  sectoral-credit, liquidity, and count series and remain `none`.
- Ratio series are intentionally not decumulated using simple differences.

Final Silver build:

- observations: 426,367
- unique series: 845
- reviewed YTD series: 46
- derived periodic series: 46
- missing source observations: 581
- duplicate observation keys: 0
