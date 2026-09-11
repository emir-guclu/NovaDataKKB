# EVDS Nature Classification Coverage Audit

## Scope

Audit source: `data/bronze/evds/metadata_raw.json`

Series audited: 118 EVDS series.

The audit evaluates whether official EVDS metadata fields can safely classify financial nature without using series-name keyword matching.

## Metadata Coverage

- Total series: 118
- `BIRIMI` populated: 92
- `DEFAULT_AGG_METHOD_STR` populated: 118
- Both populated: 92

Observed aggregation values:

- `ORTALAMA`: 55
- `BİTİŞ`: 43
- `KÜMÜLATİF`: 20

The prompt-level assumptions `TOPLAM` and `SON` do not occur in the current metadata snapshot.

## Rejected Broad Heuristics

A broad metadata heuristic was tested using unit and aggregation fields.

Result:

- Automatically classified: 71 / 118
- Unclassified: 47 / 118
- Conflicts with reviewed classification: 36 / 71 classified series

This conflict rate is too high for canonical financial semantics.

Examples include:

- `bin TL` credit-volume series incorrectly becoming `price`
- `BİTİŞ` unemployment-rate series incorrectly becoming `stock`
- index series being confused with prices
- mixed-unit funding series being misclassified

Therefore `TL`, `USD`, `EUR`, `Endeks`, `BİTİŞ`, and `ORTALAMA` are not considered sufficient standalone evidence for automatic nature classification.

## High-Confidence Rules

Two metadata rules were validated against the current reviewed EVDS catalog:

### `DEFAULT_AGG_METHOD_STR = KÜMÜLATİF`

- Series: 20
- Expected nature: `flow`
- Conflicts with reviewed classification: 0

Decision: safe automatic classification rule.

### Pure Rate Unit

Exact normalized unit in:

- `%`
- `YÜZDE`
- `YUZDE`
- `ORAN`
- `PUAN`

- Series observed: 2
- Expected nature: `rate`
- Conflicts with reviewed classification: 0

Decision: safe automatic classification rule.

## Automatic Classification Policy

For unknown/on-demand EVDS series:

1. `DEFAULT_AGG_METHOD_STR = KÜMÜLATİF` -> `flow`
2. Pure rate unit -> `rate`
3. Otherwise -> `unclassified`

Automatically classified series are marked `nature_reviewed = False`.

Existing manually reviewed/category-reviewed EVDS and BDDK classifications remain `nature_reviewed = True`.

No series-name keyword matching is used.

## Rationale

The classifier intentionally prioritizes semantic precision over coverage. An unresolved series should remain `unclassified` and enter review rather than receive a plausible but financially incorrect nature.

This protects downstream alignment and Gold semantics from silent classification errors.

## EVDS KÜMÜLATİF Semantics Verification

TCMB EVDS official documentation defines `aggregation_types` as the aggregation method applied when retrieving/transforming series frequency. In that contract, `KÜMÜLATİF` corresponds to `sum`. Therefore `DEFAULT_AGG_METHOD_STR=KÜMÜLATİF` is an aggregation instruction, not evidence that the stored observation itself is a YTD/running-total level. This is semantically different from BDDK `accumulation=ytd`, where the raw series is an accumulated level and must not be summed again. For unknown EVDS series, `KÜMÜLATİF -> flow` remains a conservative automatic signal and always produces `nature_reviewed=False` until human review.
