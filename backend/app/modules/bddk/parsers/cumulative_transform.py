"""Generate periodic BDDK series from reviewed cumulative observations."""

from __future__ import annotations

import pandas as pd

from app.modules.bddk.parsers.decumulate import decumulate
from app.modules.bddk.parsers.series_catalog import (
    get_accumulation,
)


def add_periodic_series(
    observations: pd.DataFrame,
) -> pd.DataFrame:
    """
    Preserve raw observations and append *_periodic series
    for explicitly reviewed cumulative series.

    The original cumulative series remains unchanged.

    For a YTD series:
        Jan periodic = Jan YTD
        Feb periodic = Feb YTD - Jan YTD
        ...
        January of a new year resets automatically.
    """
    required = {
        "series_id",
        "date",
        "value",
        "dims",
        "source",
        "freq",
        "unit",
        "period_start",
        "period_end",
    }

    missing = required - set(observations.columns)

    if missing:
        raise ValueError(
            "Missing required observation columns for "
            f"periodic generation: {sorted(missing)}"
        )

    base = observations.copy()

    base["date"] = pd.to_datetime(
        base["date"],
        errors="raise",
    )

    cumulative_ids = [
        series_id
        for series_id in base["series_id"].unique()
        if get_accumulation(series_id) != "none"
    ]

    periodic_parts: list[pd.DataFrame] = []

    for series_id in sorted(cumulative_ids):
        accumulation = get_accumulation(series_id)

        series_rows = base[
            base["series_id"] == series_id
        ].copy()

        if series_rows.empty:
            continue

        for dims, group in series_rows.groupby(
            "dims",
            dropna=False,
            sort=True,
        ):
            group = group.sort_values(
                "date",
                kind="stable",
            ).copy()

            if group["date"].duplicated().any():
                raise ValueError(
                    "Cumulative series contains duplicate dates "
                    f"for series_id={series_id!r}, dims={dims!r}"
                )

            values = pd.Series(
                group["value"].to_numpy(),
                index=pd.DatetimeIndex(group["date"]),
                dtype="float64",
            )

            periodic_values = decumulate(
                values,
                accumulation=accumulation,
            )

            periodic = group.copy()

            periodic["series_id"] = (
                periodic["series_id"]
                + "_periodic"
            )

            periodic["value"] = (
                periodic_values
                .reindex(
                    pd.DatetimeIndex(periodic["date"])
                )
                .to_numpy()
            )

            periodic_parts.append(periodic)

    if not periodic_parts:
        return base.sort_values(
            ["series_id", "date", "dims"],
            kind="stable",
        ).reset_index(drop=True)

    periodic_df = pd.concat(
        periodic_parts,
        ignore_index=True,
    )

    result = pd.concat(
        [
            base,
            periodic_df,
        ],
        ignore_index=True,
    )

    duplicate_key = [
        "series_id",
        "date",
        "dims",
    ]

    duplicate_mask = result.duplicated(
        duplicate_key,
        keep=False,
    )

    if duplicate_mask.any():
        examples = result.loc[
            duplicate_mask,
            duplicate_key + ["value"],
        ].head(20)

        raise ValueError(
            "Periodic generation produced duplicate "
            "(series_id, date, dims) observations:\n"
            f"{examples.to_string(index=False)}"
        )

    return result.sort_values(
        ["series_id", "date", "dims"],
        kind="stable",
    ).reset_index(drop=True)
