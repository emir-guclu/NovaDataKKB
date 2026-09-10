"""On-demand EVDS series ingestion, canonicalization, and DuckDB registration service.

Enables on-the-fly fetching of non-manifest or newly requested EVDS series:
1. Ingests raw Bronze JSON via EvdsClient and saves to data/bronze/evds/{series_code}.json
2. Synchronizes official CBRT metadata into metadata_raw.json
3. Transforms to local EVDS Silver Parquet (observations.parquet, series_metadata.parquet)
4. Standardizes according to Canonical Silver contract:
   - Sets date = period_end
   - Enriches with unit from metadata
   - Formats dims as canonical JSON
   - Validates via CanonicalObservation and CanonicalSeriesMetadata (Pydantic v2)
5. Idempotently registers/inserts into data/silver/silver.duckdb (if add_to_silver=True)
6. Returns rich summary and preview for immediate LLM response.
"""

from __future__ import annotations

import json
import logging
from datetime import date as dt_date
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import duckdb
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from app.services.series_nature import classify_series_nature
from app.models.silver_canonical import (
    CanonicalObservation,
    CanonicalSeriesMetadata,
)
from app.modules.evds.catalog_store import load_catalog
from app.modules.evds.client import EvdsClient
from app.modules.evds.metadata import sync_metadata
from app.modules.evds.transformer import (
    OBSERVATIONS_SCHEMA,
    SERIES_METADATA_SCHEMA,
    build_series_dimension_row,
    clean_observation_value,
    compute_period_boundaries,
    extract_series_dims,
    extract_series_value_key,
    parse_evds_date,
    resolve_canonical_freq,
    transform_single_series,
    write_parquet_atomic,
)

logger = logging.getLogger("evds_loader")

BACKEND_DIR = Path(__file__).resolve().parents[2]
DEFAULT_BRONZE_DIR = BACKEND_DIR.parent / "data" / "bronze" / "evds"
DEFAULT_SILVER_DIR = BACKEND_DIR.parent / "data" / "silver" / "evds"
DEFAULT_SILVER_DB = BACKEND_DIR.parent / "data" / "silver" / "silver.duckdb"
DEFAULT_METADATA_RAW = DEFAULT_BRONZE_DIR / "metadata_raw.json"
DEFAULT_CATALOG_PATH = DEFAULT_BRONZE_DIR / "evds_catalog.parquet"


def _normalize_series_code(code: str) -> str:
    """Strips any source prefix, e.g. 'EVDS:TP.DK.USD.A.YTL' -> 'TP.DK.USD.A.YTL'."""
    clean = code.strip()
    if clean.startswith("EVDS:"):
        clean = clean.split(":", 1)[1]
    return clean


def _upsert_parquet_table(
    target_path: Path,
    new_df: pd.DataFrame,
    schema: pa.Schema,
    key_column: str = "series_id",
) -> None:
    """Idempotently upserts rows for a series into an existing Parquet file."""
    if target_path.exists() and target_path.stat().st_size > 0:
        existing_table = pq.read_table(target_path)
        existing_df = existing_table.to_pandas()
        series_id_val = new_df[key_column].iloc[0]
        retained_df = existing_df[existing_df[key_column] != series_id_val]
        combined_df = pd.concat([retained_df, new_df], ignore_index=True)
    else:
        combined_df = new_df

    if "date" in combined_df.columns:
        combined_df = combined_df.sort_values(
            [key_column, "date"], ascending=[True, True]
        ).reset_index(drop=True)
    else:
        combined_df = combined_df.sort_values(
            key_column, ascending=True
        ).reset_index(drop=True)

    table = pa.Table.from_pandas(combined_df, schema=schema, preserve_index=False)
    write_parquet_atomic(table, target_path)


def load_evds_series(
    series_code: str,
    start_date: str = "01-01-2021",
    end_date: str = "01-06-2026",
    add_to_silver: bool = True,
    client: Optional[EvdsClient] = None,
    bronze_dir: Optional[Path] = None,
    silver_dir: Optional[Path] = None,
    silver_db_path: Optional[Path] = None,
    metadata_raw_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Ingests, transforms, canonicalizes, and registers a single EVDS series on-demand.

    Args:
        series_code: Raw or prefixed EVDS series code (e.g. 'TP.DK.REER.YTL').
        start_date: Start date in DD-MM-YYYY format.
        end_date: End date in DD-MM-YYYY format.
        add_to_silver: If True, writes canonical rows into silver.duckdb.
        client: Optional EvdsClient instance (useful for mocking).
        bronze_dir: Optional override for data/bronze/evds directory.
        silver_dir: Optional override for data/silver/evds directory.
        silver_db_path: Optional override for data/silver/silver.duckdb path.
        metadata_raw_path: Optional override for metadata_raw.json path.

    Returns:
        Summary dict containing series info, row counts, preview, and silver status.
    """
    code = _normalize_series_code(series_code)
    series_id = f"EVDS:{code}"

    b_dir = bronze_dir or DEFAULT_BRONZE_DIR
    s_dir = silver_dir or DEFAULT_SILVER_DIR
    db_path = silver_db_path or DEFAULT_SILVER_DB
    meta_path = metadata_raw_path or DEFAULT_METADATA_RAW

    b_dir.mkdir(parents=True, exist_ok=True)
    s_dir.mkdir(parents=True, exist_ok=True)

    # 1. Fetch Bronze Observations JSON
    if client is None:
        client = EvdsClient()

    logger.info(f"Fetching Bronze observations for {code} ({start_date} to {end_date})...")
    raw_payload = client.get_data(
        series_code=code,
        start_date=start_date,
        end_date=end_date,
        raw=True,
    )

    if not raw_payload or not isinstance(raw_payload, list) or len(raw_payload) == 0:
        raise ValueError(f"EVDS returned no observation data for series {code!r}")

    raw_json_file = b_dir / f"{code}.json"
    with open(raw_json_file, "w", encoding="utf-8") as f:
        json.dump(raw_payload, f, ensure_ascii=False, indent=2)

    # 2. Synchronize / Load Official Metadata
    meta_dict: Dict[str, Any] = {}
    if meta_path.exists():
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                meta_dict = json.load(f)
        except Exception:
            meta_dict = {}

    meta_info = meta_dict.get(code)
    if not meta_info:
        # Fetch datagroup / series metadata via client if possible
        try:
            cat_info = client.get_series_metadata(code)
            if cat_info and isinstance(cat_info, list) and len(cat_info) > 0:
                meta_info = cat_info[0]
            elif isinstance(cat_info, dict):
                meta_info = cat_info
        except Exception as err:
            logger.warning(f"Could not fetch live metadata for {code}: {err}")

        if not meta_info:
            # Fallback basic metadata structure
            meta_info = {
                "SERIE_CODE": code,
                "SERIE_NAME": code,
                "FREQUENCY_STR": "AYLIK",
                "DATAGROUP_NAME": "Genel",
                "BIRIMI": None,
                "NOTE": None,
                "TAG": [],
            }

        meta_dict[code] = meta_info
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta_dict, f, ensure_ascii=False, indent=2)

    # 3. Transform to EVDS Silver Parquet format
    raw_obs_rows = transform_single_series(code, raw_payload, meta_info)
    if not raw_obs_rows:
        raise ValueError(f"No valid numeric observations could be parsed for {code!r}")

    dim_row = build_series_dimension_row(code, meta_info)

    # Upsert local EVDS Parquet files
    obs_parquet = s_dir / "observations.parquet"
    meta_parquet = s_dir / "series_metadata.parquet"

    raw_obs_df = pd.DataFrame(raw_obs_rows)
    dim_df = pd.DataFrame([dim_row])

    _upsert_parquet_table(obs_parquet, raw_obs_df, OBSERVATIONS_SCHEMA, "series_id")
    _upsert_parquet_table(meta_parquet, dim_df, SERIES_METADATA_SCHEMA, "series_id")

    # 4. Canonical Transformation (Enforce Canonical Silver Rules)
    canonical_obs_rows = []
    unit_val = meta_info.get("BIRIMI")
    source_file_val = f"{code}.json"

    for r in raw_obs_rows:
        # Canonical rule: date equals period_end
        p_end = r["period_end"]
        if isinstance(p_end, dt_date):
            c_date = p_end
        else:
            c_date = pd.to_datetime(p_end).date()

        # Parse dims
        dims_val = r.get("dims")
        if isinstance(dims_val, str):
            try:
                parsed_dims = json.loads(dims_val)
            except Exception:
                parsed_dims = {}
        elif isinstance(dims_val, dict):
            parsed_dims = dims_val
        else:
            parsed_dims = {}

        obs_model = CanonicalObservation(
            series_id=series_id,
            source="EVDS",
            date=c_date,
            period_start=r["period_start"],
            period_end=r["period_end"],
            value=r["value"],
            freq=r["freq"],
            unit=unit_val,
            dims=parsed_dims,
            source_file=source_file_val,
        )
        canonical_obs_rows.append(obs_model.model_dump())

    nature, alignment_override = classify_series_nature(
        series_id=series_id,
        source="EVDS",
        category=dim_row.get("category", "genel"),
        accumulation="none",
    )

    meta_model = CanonicalSeriesMetadata(
        series_id=series_id,
        source="EVDS",
        series_code=code,
        series_name=meta_info.get("SERIE_NAME") or code,
        category=dim_row.get("category", "genel"),
        freq=dim_row.get("freq", "M"),
        unit=unit_val,
        description=meta_info.get("NOTE"),
        tags=dim_row.get("tags", []),
        accumulation="none",
        is_cumulative=False,
        nature=nature,
        alignment_override=alignment_override,
    )
    canonical_meta_dict = meta_model.model_dump()

    if add_to_silver and nature == "unclassified":
        raise ValueError(
            f"Series {series_id!r} has unclassified financial nature; "
            "cannot add it to canonical Silver."
        )

    # 5. Insert into silver.duckdb if requested
    added_to_silver = False
    if add_to_silver and db_path.exists():
        canonical_obs_df = pd.DataFrame(canonical_obs_rows)
        # Ensure dims is string JSON for DuckDB JSON column
        canonical_obs_df["dims"] = canonical_obs_df["dims"].map(
            lambda d: json.dumps(d, ensure_ascii=False)
        )
        canonical_meta_df = pd.DataFrame([canonical_meta_dict])

        con = duckdb.connect(str(db_path))
        try:
            # Idempotently delete existing records
            con.execute("DELETE FROM observations WHERE series_id = ?", [series_id])
            con.execute("DELETE FROM series_metadata WHERE series_id = ?", [series_id])

            con.register("_new_canonical_obs", canonical_obs_df)
            con.execute(
                """
                INSERT INTO observations
                SELECT
                    CAST(series_id AS VARCHAR),
                    CAST(source AS VARCHAR),
                    CAST(date AS DATE),
                    CAST(period_start AS DATE),
                    CAST(period_end AS DATE),
                    CAST(value AS DOUBLE),
                    CAST(freq AS VARCHAR),
                    CAST(unit AS VARCHAR),
                    CAST(dims AS JSON),
                    CAST(source_file AS VARCHAR)
                FROM _new_canonical_obs
                """
            )

            con.register("_new_canonical_meta", canonical_meta_df)
            con.execute(
                """
                INSERT INTO series_metadata
                SELECT
                    CAST(series_id AS VARCHAR),
                    CAST(source AS VARCHAR),
                    CAST(series_code AS VARCHAR),
                    CAST(series_name AS VARCHAR),
                    CAST(category AS VARCHAR),
                    CAST(freq AS VARCHAR),
                    CAST(unit AS VARCHAR),
                    CAST(description AS VARCHAR),
                    tags,
                    CAST(accumulation AS VARCHAR),
                    CAST(is_cumulative AS BOOLEAN),
                    CAST(nature AS VARCHAR),
                    CAST(alignment_override AS VARCHAR)
                FROM _new_canonical_meta
                """
            )
            added_to_silver = True
            logger.info(
                f"Successfully inserted {len(canonical_obs_rows)} rows into {db_path.name}"
            )
        finally:
            con.close()

    # 6. Build preview
    sorted_obs = sorted(canonical_obs_rows, key=lambda x: x["date"])
    preview = [
        {"date": str(o["date"]), "value": o["value"]}
        for o in sorted_obs[-5:]
    ]

    return {
        "status": "success",
        "series_id": series_id,
        "series_code": code,
        "series_name": canonical_meta_dict["series_name"],
        "freq": canonical_meta_dict["freq"],
        "unit": unit_val,
        "rows_count": len(canonical_obs_rows),
        "first_date": str(sorted_obs[0]["date"]),
        "last_date": str(sorted_obs[-1]["date"]),
        "latest_value": sorted_obs[-1]["value"],
        "added_to_silver": added_to_silver,
        "preview": preview,
    }
