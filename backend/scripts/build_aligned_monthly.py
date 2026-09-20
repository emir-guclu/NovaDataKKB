"""Build the monthly aligned analytical layer from canonical Silver.

Input:
    data/silver/silver.duckdb

Output:
    data/aligned/monthly/observations.parquet
    data/aligned/monthly/series_metadata.parquet
    data/aligned/monthly/aligned.duckdb

This is a pre-Gold layer. It preserves explicit alignment semantics and
does not silently invent aggregation rules.
"""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import duckdb

from app.services.align_service import align_to_monthly
from app.services.alignment_policies import build_alignment_policies


ROOT = Path(__file__).resolve().parents[2]

SILVER_DB = (
    ROOT
    / "data"
    / "silver"
    / "silver.duckdb"
)

OUTPUT_DIR = (
    ROOT
    / "data"
    / "aligned"
    / "monthly"
)

OBS_OUTPUT = OUTPUT_DIR / "observations.parquet"
META_OUTPUT = OUTPUT_DIR / "series_metadata.parquet"
DUCKDB_OUTPUT = OUTPUT_DIR / "aligned.duckdb"


def load_canonical_silver():
    if not SILVER_DB.exists():
        raise FileNotFoundError(
            f"Canonical Silver database not found: {SILVER_DB}"
        )

    con = duckdb.connect(
        str(SILVER_DB),
        read_only=True,
    )

    try:
        observations = con.execute(
            """
            SELECT
                series_id,
                source,
                date,
                period_start,
                period_end,
                value,
                freq,
                unit,
                dims,
                source_file
            FROM observations
            ORDER BY series_id, date
            """
        ).fetchdf()

        metadata = con.execute(
            """
            SELECT
                series_id,
                source,
                series_code,
                series_name,
                category,
                freq,
                unit,
                description,
                tags,
                accumulation,
                is_cumulative,
                nature,
                nature_reviewed,
                alignment_override
            FROM series_metadata
            ORDER BY series_id
            """
        ).fetchdf()

    finally:
        con.close()

    return observations, metadata


def validate_aligned(
    aligned,
    metadata,
):
    if aligned.empty:
        raise RuntimeError(
            "Alignment produced zero observations"
        )

    if set(aligned["aligned_freq"].dropna()) != {"M"}:
        raise RuntimeError(
            "Aligned output contains non-monthly rows"
        )

    duplicate_count = int(
        aligned.duplicated(
            [
                "series_id",
                "date",
                "dims",
            ]
        ).sum()
    )

    if duplicate_count:
        raise RuntimeError(
            "Aligned output contains "
            f"{duplicate_count} duplicate keys"
        )

    cumulative_ids = set(
        metadata.loc[
            metadata["accumulation"] != "none",
            "series_id",
        ]
    )

    leaked_cumulative = (
        set(aligned["series_id"])
        & cumulative_ids
    )

    if leaked_cumulative:
        raise RuntimeError(
            "Raw cumulative series leaked into aligned layer: "
            + ", ".join(
                sorted(leaked_cumulative)[:10]
            )
        )


def build_metadata(
    aligned,
    metadata,
):
    used_series = set(
        aligned["series_id"].unique()
    )

    result = metadata[
        metadata["series_id"].isin(
            used_series
        )
    ].copy()

    missing = (
        used_series
        - set(result["series_id"])
    )

    if missing:
        raise RuntimeError(
            "Aligned observations missing metadata: "
            + ", ".join(sorted(missing)[:10])
        )

    return result.sort_values(
        "series_id"
    ).reset_index(
        drop=True
    )


def write_outputs(
    aligned,
    aligned_metadata,
):
    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    aligned.to_parquet(
        OBS_OUTPUT,
        index=False,
    )

    aligned_metadata.to_parquet(
        META_OUTPUT,
        index=False,
    )

    if DUCKDB_OUTPUT.exists():
        DUCKDB_OUTPUT.unlink()

    con = duckdb.connect(
        str(DUCKDB_OUTPUT)
    )

    try:
        con.register(
            "aligned_df",
            aligned,
        )

        con.register(
            "metadata_df",
            aligned_metadata,
        )

        con.execute(
            """
            CREATE TABLE observations AS
            SELECT
                series_id,
                source,
                CAST(date AS DATE) AS date,
                value,
                source_freq,
                aligned_freq,
                unit,
                CAST(dims AS JSON) AS dims,
                alignment_method,
                is_imputed
            FROM aligned_df
            ORDER BY
                series_id,
                dims,
                date
            """
        )

        con.execute(
            """
            CREATE TABLE series_metadata AS
            SELECT *
            FROM metadata_df
            ORDER BY series_id
            """
        )

    finally:
        con.close()


def print_audit(
    aligned,
    aligned_metadata,
):
    print()
    print("MONTHLY ALIGNMENT BUILD COMPLETE")
    print("=" * 70)

    print(
        f"Observations: {len(aligned):,}"
    )

    print(
        "Series:",
        f"{aligned['series_id'].nunique():,}",
    )

    print()
    print("BY SOURCE / SOURCE FREQUENCY")

    summary = (
        aligned.groupby(
            [
                "source",
                "source_freq",
                "alignment_method",
            ],
            dropna=False,
        )
        .agg(
            rows=("series_id", "size"),
            series=("series_id", "nunique"),
        )
        .reset_index()
    )

    print(
        summary.to_string(
            index=False
        )
    )

    print()
    print(
        "Imputed rows:",
        int(aligned["is_imputed"].sum()),
    )

    print(
        "Metadata rows:",
        len(aligned_metadata),
    )

    print(
        "Duplicate keys:",
        int(
            aligned.duplicated(
                [
                    "series_id",
                    "date",
                    "dims",
                ]
            ).sum()
        ),
    )

    print()
    print("OUTPUTS")
    print(OBS_OUTPUT)
    print(META_OUTPUT)
    print(DUCKDB_OUTPUT)


def main():
    observations, metadata = (
        load_canonical_silver()
    )

    policies = build_alignment_policies(
        metadata
    )

    print(
        "Canonical observations:",
        f"{len(observations):,}",
    )

    print(
        "Canonical metadata series:",
        f"{len(metadata):,}",
    )

    print(
        "Explicit D/W policies:",
        f"{len(policies):,}",
    )

    supported_freqs = {"D", "W", "M", "Q"}

    alignment_observations = observations[
        observations["freq"].isin(supported_freqs)
    ].copy()

    alignment_metadata = metadata[
        metadata["freq"].isin(supported_freqs)
    ].copy()

    skipped_freqs = sorted(
        set(metadata["freq"].dropna())
        - supported_freqs
    )

    if skipped_freqs:
        print(
            "Skipping unsupported source frequencies "
            f"for monthly alignment: {', '.join(skipped_freqs)}"
        )

    aligned = align_to_monthly(
        alignment_observations,
        alignment_metadata,
        policies,
        quarterly_policy="sparse",
    )

    validate_aligned(
        aligned,
        alignment_metadata,
    )

    aligned_metadata = build_metadata(
        aligned,
        alignment_metadata,
    )

    write_outputs(
        aligned,
        aligned_metadata,
    )

    print_audit(
        aligned,
        aligned_metadata,
    )


if __name__ == "__main__":
    main()
