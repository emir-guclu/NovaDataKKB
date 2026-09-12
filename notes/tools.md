# Tool Notes

## Anomaly Detection Future Mode

Initial `anomaly_detection` should work on one selected time series from
`gold_periodic_change`.

Expected first-version inputs:

- `series_id`
- `dimension`
- `metric`: `value`, `mom_pct_change`, or `yoy_pct_change`
- optional `start_date` / `end_date`
- optional z-score threshold

Rationale: a single-series mode is safer for the LLM to call and easier to test
against real Gold data. A broad Lakehouse-wide anomaly scan would require extra
choices such as table, numeric column, grouping key, metric, and false-positive
handling.

Future enhancement: add a second mode that scans numeric columns in a selected
Gold table and returns the strongest anomalies across series/groups. This should
be implemented after the first single-series version is stable.
