"""Build canonical BDDK Silver observations and series catalog."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import pandas as pd

from app.modules.bddk.parsers.bddk_finturk import (
    parse_bddk_finturk,
)
from app.modules.bddk.parsers.bddk_monthly import (
    parse_bddk_monthly,
)
from app.modules.bddk.parsers.bddk_weekly import (
    parse_bddk_weekly,
)
from app.modules.bddk.parsers.cumulative_transform import (
    add_periodic_series,
)
from app.modules.bddk.parsers.series_catalog import (
    build_series_catalog,
)


ROOT = Path(__file__).resolve().parents[3]

WEEKLY_BRONZE = (
    ROOT
    / "data"
    / "bronze"
    / "bddk"
    / "weekly"
    / "bddk_weekly_all_2021_2026.csv"
)

MONTHLY_BRONZE = (
    ROOT
    / "data"
    / "bronze"
    / "bddk"
    / "monthly"
    / "bddk_monthly_all_2021_2026_precise.csv"
)

FINTURK_BRONZE = (
    ROOT
    / "data"
    / "bronze"
    / "bddk"
    / "finturk"
    / "bddk_finturk_all_2021_2026.csv"
)

SILVER_DIR = (
    ROOT
    / "data"
    / "silver"
    / "bddk"
)

OBSERVATIONS_OUT = (
    SILVER_DIR
    / "observations.parquet"
)

CATALOG_OUT = (
    SILVER_DIR
    / "series_metadata.parquet"
)


OBSERVATION_COLUMNS = [
    "series_id",
    "source",
    "date",
    "period_start",
    "period_end",
    "value",
    "freq",
    "unit",
    "dims",
    "source_file",
]

CATALOG_COLUMNS = [
    "series_id",
    "source",
    "freq",
    "unit",
    "accumulation",
    "description",
    "is_cumulative",
    "nature",
    "nature_reviewed",
    "alignment_override",
]


def _require_file(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(
            f"Required Bronze file does not exist: {path}"
        )


def _atomic_to_parquet(
    df: pd.DataFrame,
    destination: Path,
) -> None:
    """
    Write parquet atomically.

    The temporary file is created in the same directory so os.replace()
    stays atomic on the same filesystem.
    """
    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    fd, temp_name = tempfile.mkstemp(
        prefix=f".{destination.stem}.",
        suffix=".tmp.parquet",
        dir=destination.parent,
    )

    os.close(fd)

    temp_path = Path(temp_name)

    try:
        df.to_parquet(
            temp_path,
            index=False,
        )

        os.replace(
            temp_path,
            destination,
        )

    except Exception:
        temp_path.unlink(
            missing_ok=True,
        )
        raise


def _validate_json_dims(
    observations: pd.DataFrame,
) -> None:
    """
    Validate every dims value as a JSON object.

    Parquet stores the serialized representation; downstream DuckDB
    should CAST dims AS JSON when materializing the canonical table.
    """
    for index, raw_dims in observations["dims"].items():
        if raw_dims is None or pd.isna(raw_dims):
            raise ValueError(
                f"NULL dims at observation row {index}"
            )

        try:
            parsed = json.loads(str(raw_dims))
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Invalid dims JSON at observation row {index}: "
                f"{raw_dims!r}"
            ) from exc

        if not isinstance(parsed, dict):
            raise ValueError(
                f"dims must be a JSON object at row {index}, "
                f"got {type(parsed).__name__}"
            )


def _validate_observations(
    observations: pd.DataFrame,
) -> None:
    missing = (
        set(OBSERVATION_COLUMNS)
        - set(observations.columns)
    )

    if missing:
        raise ValueError(
            "Final Silver observations are missing columns: "
            f"{sorted(missing)}"
        )

    observations = observations[
        OBSERVATION_COLUMNS
    ]

    required_non_null = [
        "series_id",
        "source",
        "date",
        "period_start",
        "period_end",
        "freq",
        "unit",
        "dims",
    ]

    for column in required_non_null:
        if observations[column].isna().any():
            raise ValueError(
                f"Final Silver contains NULL {column}"
            )

    if (
        observations["unit"]
        .astype(str)
        .str.strip()
        .eq("")
        .any()
    ):
        raise ValueError(
            "Final Silver contains blank unit values"
        )

    allowed_freqs = {
        "W",
        "M",
        "Q",
        "Y",
        "D",
    }

    unexpected_freqs = (
        set(observations["freq"].unique())
        - allowed_freqs
    )

    if unexpected_freqs:
        raise ValueError(
            "Unexpected frequencies in Final Silver: "
            f"{sorted(unexpected_freqs)}"
        )

    for column in [
        "date",
        "period_start",
        "period_end",
    ]:
        observations[column] = pd.to_datetime(
            observations[column],
            errors="raise",
        )

    invalid_bounds = (
        (
            observations["period_start"]
            > observations["period_end"]
        )
        | (
            observations["date"]
            != observations["period_end"]
        )
    )

    if invalid_bounds.any():
        examples = observations.loc[
            invalid_bounds,
            [
                "series_id",
                "date",
                "period_start",
                "period_end",
            ],
        ].head(20)

        raise ValueError(
            "Invalid Silver period boundaries:\n"
            f"{examples.to_string(index=False)}"
        )

    duplicate_mask = observations.duplicated(
        [
            "series_id",
            "date",
            "dims",
        ],
        keep=False,
    )

    if duplicate_mask.any():
        examples = observations.loc[
            duplicate_mask,
            [
                "series_id",
                "date",
                "dims",
                "value",
            ],
        ].head(20)

        raise ValueError(
            "Duplicate final Silver observations:\n"
            f"{examples.to_string(index=False)}"
        )

    _validate_json_dims(
        observations
    )


def _validate_catalog(
    catalog: pd.DataFrame,
    observations: pd.DataFrame,
) -> None:
    missing = (
        set(CATALOG_COLUMNS)
        - set(catalog.columns)
    )

    if missing:
        raise ValueError(
            "Series catalog is missing columns: "
            f"{sorted(missing)}"
        )

    if catalog["series_id"].duplicated().any():
        raise ValueError(
            "Series catalog contains duplicate series_id"
        )

    if catalog["series_id"].isna().any():
        raise ValueError(
            "Series catalog contains NULL series_id"
        )

    observation_ids = set(
        observations["series_id"].unique()
    )

    catalog_ids = set(
        catalog["series_id"].unique()
    )

    missing_catalog = (
        observation_ids
        - catalog_ids
    )

    orphan_catalog = (
        catalog_ids
        - observation_ids
    )

    if missing_catalog:
        raise ValueError(
            "Observation series missing from catalog: "
            f"{sorted(missing_catalog)[:20]}"
        )

    if orphan_catalog:
        raise ValueError(
            "Catalog contains series with no observations: "
            f"{sorted(orphan_catalog)[:20]}"
        )


def build() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build all BDDK Silver observations and catalog."""
    for path in [
        WEEKLY_BRONZE,
        MONTHLY_BRONZE,
        FINTURK_BRONZE,
    ]:
        _require_file(path)

    print("Reading Bronze files...")

    weekly_raw = pd.read_csv(
        WEEKLY_BRONZE,
    )

    monthly_raw = pd.read_csv(
        MONTHLY_BRONZE,
    )

    finturk_raw = pd.read_csv(
        FINTURK_BRONZE,
    )

    print("Parsing Weekly...")
    weekly = parse_bddk_weekly(
        weekly_raw,
        source_file=WEEKLY_BRONZE.name,
    )

    print("Parsing Monthly...")
    monthly_raw_silver = parse_bddk_monthly(
        monthly_raw,
        source_file=MONTHLY_BRONZE.name,
    )

    print("Generating reviewed periodic Monthly series...")
    monthly = add_periodic_series(
        monthly_raw_silver
    )

    print("Parsing FinTürk...")
    finturk = parse_bddk_finturk(
        finturk_raw,
        source_file=FINTURK_BRONZE.name,
    )

    observations = pd.concat(
        [
            weekly,
            monthly,
            finturk,
        ],
        ignore_index=True,
    )

    observations = observations[
        OBSERVATION_COLUMNS
    ].copy()

    observations["date"] = pd.to_datetime(
        observations["date"],
        errors="raise",
    )

    observations["period_start"] = pd.to_datetime(
        observations["period_start"],
        errors="raise",
    )

    observations["period_end"] = pd.to_datetime(
        observations["period_end"],
        errors="raise",
    )

    observations["value"] = pd.to_numeric(
        observations["value"],
        errors="coerce",
    )

    observations = observations.sort_values(
        [
            "source",
            "series_id",
            "date",
            "dims",
        ],
        kind="stable",
    ).reset_index(drop=True)

    print("Building series catalog...")
    catalog = build_series_catalog(
        observations
    )

    catalog = catalog[
        CATALOG_COLUMNS
    ].sort_values(
        "series_id",
        kind="stable",
    ).reset_index(drop=True)

    print("Validating Final Silver...")
    _validate_observations(
        observations
    )

    _validate_catalog(
        catalog,
        observations,
    )

    return observations, catalog


def main() -> None:
    observations, catalog = build()

    print("Writing Silver observations...")
    _atomic_to_parquet(
        observations,
        OBSERVATIONS_OUT,
    )

    print("Writing series catalog...")
    _atomic_to_parquet(
        catalog,
        CATALOG_OUT,
    )

    # Re-read final artifacts instead of trusting only in-memory frames.
    persisted_observations = pd.read_parquet(
        OBSERVATIONS_OUT
    )

    persisted_catalog = pd.read_parquet(
        CATALOG_OUT
    )

    _validate_observations(
        persisted_observations
    )

    _validate_catalog(
        persisted_catalog,
        persisted_observations,
    )

    print()
    print("=" * 100)
    print("BDDK SILVER BUILD COMPLETE")
    print("=" * 100)

    print(
        "Observations:",
        len(persisted_observations),
    )

    print(
        "Series:",
        persisted_observations[
            "series_id"
        ].nunique(),
    )

    print(
        "Catalog rows:",
        len(persisted_catalog),
    )

    print(
        "Missing values:",
        int(
            persisted_observations[
                "value"
            ].isna().sum()
        ),
    )

    print(
        "Duplicate observations:",
        int(
            persisted_observations.duplicated(
                [
                    "series_id",
                    "date",
                    "dims",
                ],
                keep=False,
            ).sum()
        ),
    )

    print("\nBy source:")
    print(
        persisted_observations[
            "source"
        ]
        .value_counts()
        .to_string()
    )

    print("\nSeries by source:")
    print(
        persisted_catalog[
            "source"
        ]
        .value_counts()
        .to_string()
    )

    print("\nFrequency:")
    print(
        persisted_catalog[
            "freq"
        ]
        .value_counts()
        .to_string()
    )

    print("\nAccumulation:")
    print(
        persisted_catalog[
            "accumulation"
        ]
        .value_counts()
        .to_string()
    )

    print(
        "\nObservations parquet:",
        OBSERVATIONS_OUT,
    )

    print(
        "Catalog parquet:",
        CATALOG_OUT,
    )


if __name__ == "__main__":
    main()
