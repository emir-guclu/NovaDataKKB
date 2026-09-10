"""Flag suspicious cumulative BDDK Monthly series for manual review.

This script never changes observations or catalog metadata.
It only produces a ranked review list.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[3]

OBSERVATIONS_PATH = (
    ROOT
    / "data"
    / "silver"
    / "bddk"
    / "observations.parquet"
)

CATALOG_PATH = (
    ROOT
    / "data"
    / "silver"
    / "bddk"
    / "series_metadata.parquet"
)

OUTPUT_PATH = (
    ROOT
    / "notes"
    / "cumulative_candidates.csv"
)


def flag_monotonic_candidates(
    observations: pd.DataFrame,
    catalog: pd.DataFrame,
) -> pd.DataFrame:
    """
    Return Monthly series that deserve manual cumulative review.

    Nothing is automatically reclassified.

    Logic:
    - only BDDK Monthly series
    - catalog accumulation must currently be "none"
    - derived *_periodic series are excluded
    - inspect each series_id + dims + year independently
    - require at least 6 observations in a dims/year group
    - dims/year is monotonic when >= 90% of changes are non-negative
      and final value is above first value
    - collapse dims to one series/year decision:
      at least 80% of usable dims must show the monotonic signal
    - detect strong year-boundary resets separately
    """
    eligible_ids = set(
        catalog.loc[
            (catalog["source"] == "BDDK_MONTHLY")
            & (catalog["freq"] == "M")
            & (catalog["accumulation"] == "none")
            & ~catalog["series_id"].str.endswith(
                "_periodic"
            ),
            "series_id",
        ]
    )

    df = observations[
        observations["series_id"].isin(
            eligible_ids
        )
    ].copy()

    df["date"] = pd.to_datetime(
        df["date"],
        errors="raise",
    )

    df = df[
        df["value"].notna()
    ].copy()

    df["year"] = df["date"].dt.year

    dim_year_records: list[dict] = []

    for (
        series_id,
        dims,
        year,
    ), group in df.groupby(
        [
            "series_id",
            "dims",
            "year",
        ],
        dropna=False,
        sort=True,
    ):
        group = group.sort_values(
            "date"
        )

        if len(group) < 6:
            continue

        values = group["value"].astype(
            float
        )

        diffs = values.diff().dropna()

        if diffs.empty:
            continue

        nonnegative_ratio = float(
            (diffs >= 0).mean()
        )

        monotonic_signal = bool(
            nonnegative_ratio >= 0.90
            and values.iloc[-1]
            > values.iloc[0]
        )

        dim_year_records.append(
            {
                "series_id": series_id,
                "dims": dims,
                "year": int(year),
                "observations": len(group),
                "nonnegative_ratio": (
                    nonnegative_ratio
                ),
                "monotonic_signal": (
                    monotonic_signal
                ),
            }
        )

    dim_year = pd.DataFrame(
        dim_year_records
    )

    if dim_year.empty:
        return pd.DataFrame()

    # Collapse all dimensions into ONE result per
    # series_id + year.
    series_year = (
        dim_year.groupby(
            [
                "series_id",
                "year",
            ],
            sort=True,
        )
        .agg(
            dims_reviewed=(
                "dims",
                "size",
            ),
            monotonic_dims=(
                "monotonic_signal",
                "sum",
            ),
            avg_nonnegative_ratio=(
                "nonnegative_ratio",
                "mean",
            ),
            max_nonnegative_ratio=(
                "nonnegative_ratio",
                "max",
            ),
        )
        .reset_index()
    )

    series_year[
        "monotonic_dim_share"
    ] = (
        series_year["monotonic_dims"]
        / series_year["dims_reviewed"]
    )

    series_year[
        "monotonic_year"
    ] = (
        series_year[
            "monotonic_dim_share"
        ]
        >= 0.80
    )

    candidate_years = (
        series_year.groupby(
            "series_id",
            sort=True,
        )
        .agg(
            reviewed_years=(
                "year",
                "nunique",
            ),
            monotonic_years=(
                "monotonic_year",
                "sum",
            ),
            avg_monotonic_dim_share=(
                "monotonic_dim_share",
                "mean",
            ),
            avg_nonnegative_ratio=(
                "avg_nonnegative_ratio",
                "mean",
            ),
            max_nonnegative_ratio=(
                "max_nonnegative_ratio",
                "max",
            ),
        )
        .reset_index()
    )

    candidate_years[
        "monotonic_share"
    ] = (
        candidate_years[
            "monotonic_years"
        ]
        / candidate_years[
            "reviewed_years"
        ]
    )

    # Strong year-boundary reset detection.
    reset_records: list[dict] = []

    for (
        series_id,
        dims,
    ), group in df.groupby(
        [
            "series_id",
            "dims",
        ],
        dropna=False,
        sort=True,
    ):
        group = group.sort_values(
            "date"
        ).copy()

        yearly_edges = (
            group.groupby(
                "year"
            )
            .agg(
                first_value=(
                    "value",
                    "first",
                ),
                last_value=(
                    "value",
                    "last",
                ),
            )
            .sort_index()
        )

        reset_count = 0

        years = list(
            yearly_edges.index
        )

        for prev_year, next_year in zip(
            years,
            years[1:],
        ):
            if (
                next_year
                != prev_year + 1
            ):
                continue

            previous_end = float(
                yearly_edges.loc[
                    prev_year,
                    "last_value",
                ]
            )

            next_start = float(
                yearly_edges.loc[
                    next_year,
                    "first_value",
                ]
            )

            # Strong reset:
            # new-year first value < 40% of
            # previous year-end value.
            if (
                previous_end > 0
                and next_start
                < previous_end * 0.40
            ):
                reset_count += 1

        reset_records.append(
            {
                "series_id": series_id,
                "dims": dims,
                "reset_signals": (
                    reset_count
                ),
            }
        )

    reset_df = pd.DataFrame(
        reset_records
    )

    # For a series, use the strongest reset evidence
    # seen in any dimension.
    reset_summary = (
        reset_df.groupby(
            "series_id",
            sort=True,
        )["reset_signals"]
        .max()
        .reset_index()
    )

    result = candidate_years.merge(
        reset_summary,
        on="series_id",
        how="left",
    )

    result[
        "reset_signals"
    ] = (
        result["reset_signals"]
        .fillna(0)
        .astype(int)
    )

    # Conservative candidate filter.
    #
    # Strong candidate:
    # - monotonic in at least 3 years
    # - monotonic in >= 60% of reviewed years
    #
    # OR:
    # - monotonic in >= 2 years
    # - at least 2 strong year resets
    result = result[
        (
            (
                result[
                    "monotonic_years"
                ]
                >= 3
            )
            & (
                result[
                    "monotonic_share"
                ]
                >= 0.60
            )
        )
        |
        (
            (
                result[
                    "monotonic_years"
                ]
                >= 2
            )
            & (
                result[
                    "reset_signals"
                ]
                >= 2
            )
        )
    ].copy()

    metadata = catalog[
        [
            "series_id",
            "unit",
            "description",
        ]
    ].drop_duplicates(
        "series_id"
    )

    result = result.merge(
        metadata,
        on="series_id",
        how="left",
    )

    result[
        "review_score"
    ] = (
        result["monotonic_share"] * 2
        + result["avg_monotonic_dim_share"]
        + result["avg_nonnegative_ratio"]
        + result["reset_signals"]
    )

    result = result[
        [
            "series_id",
            "unit",
            "description",
            "reviewed_years",
            "monotonic_years",
            "monotonic_share",
            "avg_monotonic_dim_share",
            "avg_nonnegative_ratio",
            "max_nonnegative_ratio",
            "reset_signals",
            "review_score",
        ]
    ].sort_values(
        [
            "reset_signals",
            "monotonic_share",
            "review_score",
        ],
        ascending=False,
        kind="stable",
    ).reset_index(
        drop=True
    )

    if (
        result["monotonic_years"]
        > result["reviewed_years"]
    ).any():
        raise RuntimeError(
            "Invalid candidate aggregation: "
            "monotonic_years exceeds "
            "reviewed_years"
        )

    if (
        result["monotonic_share"]
        > 1
    ).any():
        raise RuntimeError(
            "Invalid candidate aggregation: "
            "monotonic_share exceeds 1"
        )

    return result


def main() -> None:
    observations = pd.read_parquet(
        OBSERVATIONS_PATH
    )

    catalog = pd.read_parquet(
        CATALOG_PATH
    )

    candidates = (
        flag_monotonic_candidates(
            observations,
            catalog,
        )
    )

    OUTPUT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    candidates.to_csv(
        OUTPUT_PATH,
        index=False,
    )

    print("=" * 100)
    print(
        "CUMULATIVE REVIEW CANDIDATES"
    )
    print("=" * 100)

    print(
        "Candidate series:",
        len(candidates),
    )

    if not candidates.empty:
        print()
        print(
            candidates.head(
                100
            ).to_string(
                index=False
            )
        )

    print()
    print(
        "Review file:",
        OUTPUT_PATH,
    )

    print()
    print(
        "IMPORTANT: No series metadata "
        "was modified."
    )


if __name__ == "__main__":
    main()
