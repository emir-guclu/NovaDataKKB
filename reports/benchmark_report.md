# NovaData Benchmark Report

- Run time: 2026-09-20T23:54:05
- Provider: `deepseek`
- Questions executed: **40**
- Successful API responses: **40/40**
- Average duration: **8.21s**
- Mean expected-tool coverage: **78.8%**
- Mean numeric coverage: **100.0%**
- Mean grounding coverage: **73.0%**

## Category summary

| Category | N | API success | Tool coverage | Numeric coverage | Avg duration |
|---|---:|---:|---:|---:|---:|
| anomaly_shock | 5 | 100.0% | 40.0% | 100.0% | 11.63s |
| cross_market | 6 | 100.0% | 66.7% | 100.0% | 10.73s |
| edge_case | 5 | 100.0% | 100.0% | 100.0% | 5.69s |
| finturk_geo | 6 | 100.0% | 83.3% | 100.0% | 4.86s |
| live_evds | 3 | 100.0% | 83.3% | 100.0% | 11.88s |
| single_metric | 8 | 100.0% | 87.5% | 100.0% | 6.92s |
| trend_change | 7 | 100.0% | 85.7% | 100.0% | 8.15s |

## Per-question results

| ID | Category | Sec | Tools | Numeric | Text | Grounding | Status |
|---|---|---:|---:|---:|---:|---:|---|
| single_01 | single_metric | 8.96 | 100% | 100% | 100% | 83% | PASS |
| single_02 | single_metric | 6.76 | 100% | 100% | 100% | 50% | PASS |
| single_03 | single_metric | 13.31 | 100% | 100% | 100% | 89% | PASS |
| single_04 | single_metric | 5.05 | 0% | 100% | 100% | 83% | PASS |
| single_05 | single_metric | 5.84 | 100% | 100% | 100% | 60% | PASS |
| single_06 | single_metric | 7.58 | 100% | 100% | 100% | 50% | PASS |
| single_07 | single_metric | 5.63 | 100% | 100% | 100% | 60% | PASS |
| single_08 | single_metric | 2.22 | 100% | 100% | 100% | 100% | PASS |
| trend_01 | trend_change | 9.25 | 100% | 100% | 100% | 45% | PASS |
| trend_02 | trend_change | 7.37 | 100% | 100% | 100% | 31% | PASS |
| trend_03 | trend_change | 7.94 | 100% | 100% | 100% | 67% | PASS |
| trend_04 | trend_change | 6.39 | 0% | 100% | 100% | 40% | PASS |
| trend_05 | trend_change | 14.72 | 100% | 100% | 100% | 82% | PASS |
| trend_06 | trend_change | 4.23 | 100% | 100% | 100% | 76% | PASS |
| trend_07 | trend_change | 7.17 | 100% | 100% | 100% | 63% | PASS |
| relation_01 | cross_market | 9.93 | 100% | 100% | 100% | 100% | PASS |
| relation_02 | cross_market | 12.65 | 50% | 100% | 100% | 100% | PASS |
| relation_03 | cross_market | 7.93 | 50% | 100% | 100% | 100% | PASS |
| relation_04 | cross_market | 8.81 | 50% | 100% | 100% | 100% | PASS |
| relation_05 | cross_market | 11.06 | 50% | 100% | 100% | 89% | PASS |
| relation_06 | cross_market | 14.03 | 100% | 100% | 100% | 75% | PASS |
| finturk_01 | finturk_geo | 4.61 | 100% | 100% | 100% | 40% | PASS |
| finturk_02 | finturk_geo | 6.72 | 100% | 100% | 100% | 67% | PASS |
| finturk_03 | finturk_geo | 3.52 | 100% | 100% | 100% | 60% | PASS |
| finturk_04 | finturk_geo | 4.51 | 50% | 100% | 100% | 14% | PASS |
| finturk_05 | finturk_geo | 3.38 | 100% | 100% | 100% | 45% | PASS |
| finturk_06 | finturk_geo | 6.45 | 50% | 100% | 100% | 80% | PASS |
| anomaly_01 | anomaly_shock | 7.48 | 0% | 100% | 100% | 60% | PASS |
| anomaly_02 | anomaly_shock | 7.99 | 50% | 100% | 100% | 62% | PASS |
| anomaly_03 | anomaly_shock | 14.44 | 0% | 100% | 100% | 69% | PASS |
| anomaly_04 | anomaly_shock | 7.88 | 50% | 100% | 100% | 67% | PASS |
| anomaly_05 | anomaly_shock | 20.38 | 100% | 100% | 100% | 100% | PASS |
| live_01 | live_evds | 8.09 | 100% | 100% | 100% | 100% | PASS |
| live_02 | live_evds | 21.30 | 100% | 100% | 100% | 100% | PASS |
| live_03 | live_evds | 6.24 | 50% | 100% | 100% | 71% | PASS |
| edge_01 | edge_case | 5.12 | 100% | 100% | 100% | 100% | PASS |
| edge_02 | edge_case | 8.34 | 100% | 100% | 100% | 67% | PASS |
| edge_03 | edge_case | 3.43 | 100% | 100% | 100% | — | PASS |
| edge_04 | edge_case | 7.15 | 100% | 100% | 100% | 100% | PASS |
| edge_05 | edge_case | 4.43 | 100% | 100% | 100% | 100% | PASS |

## Items requiring review

No failed/check items.
