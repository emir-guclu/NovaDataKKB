# Alignment Mean Semantics and Time Weighting

## Current behavior

The `mean` alignment method uses the simple arithmetic mean of the available observations that fall inside the target period.

Each available observation contributes equally. The current implementation does not weight observations by the number of calendar days they represent.

## Weekly-to-monthly boundaries

When weekly observations are aligned to a monthly target, each available weekly observation assigned to that month receives equal weight in the arithmetic mean.

Partial weeks that overlap month boundaries are not prorated and are not day-weighted. No synthetic observations are created for missing weekends, holidays, or uncovered days.

## Why this is explicit

This behavior avoids silently introducing assumptions about intra-period exposure or data availability. If a series later requires a time-weighted mean, prorated boundary treatment, or another exceptional aggregation rule, that behavior must be introduced explicitly through reviewed metadata or a dedicated alignment policy rather than by changing the meaning of `mean` silently.
