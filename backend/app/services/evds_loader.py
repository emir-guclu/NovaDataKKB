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
from typing import Any, Dict, List, Literal, Optional, Union

import duckdb
import pandas as pd

from app.models.silver_canonical import (
    CanonicalObservation,
    CanonicalSeriesMetadata,
)
from app.modules.evds.catalog_store import load_catalog
from app.modules.evds.client import EvdsClient
from app.modules.evds.metadata import sync_metadata
from app.services.align_service import align_to_monthly
from app.services.aligned_store import upsert_single_series_to_aligned_duckdb
from app.services.alignment_policies import build_alignment_policies
from app.modules.evds.transformer import (
    build_series_dimension_row,
    clean_observation_value,
    compute_period_boundaries,
    extract_series_dims,
    extract_series_value_key,
    parse_evds_date,
    resolve_canonical_freq,
    transform_single_series,
    upsert_single_series_to_silver_parquet,
)

logger = logging.getLogger("evds_loader")


def _upsert_embedding_catalog_series(**kwargs: Any) -> bool:
    try:
        from backend.scripts.generate_catalog_embeddings import (
            upsert_embedding_catalog_series,
        )
    except ModuleNotFoundError:
        from scripts.generate_catalog_embeddings import (
            upsert_embedding_catalog_series,
        )

    return upsert_embedding_catalog_series(**kwargs)

BACKEND_DIR = Path(__file__).resolve().parents[2]
DEFAULT_BRONZE_DIR = BACKEND_DIR.parent / "data" / "bronze" / "evds"
DEFAULT_SILVER_DIR = BACKEND_DIR.parent / "data" / "silver" / "evds"
DEFAULT_SILVER_DB = BACKEND_DIR.parent / "data" / "silver" / "silver.duckdb"
DEFAULT_ALIGNED_DB = BACKEND_DIR.parent / "data" / "aligned" / "monthly" / "aligned.duckdb"
DEFAULT_METADATA_RAW = DEFAULT_BRONZE_DIR / "metadata_raw.json"
DEFAULT_CATALOG_PATH = DEFAULT_BRONZE_DIR / "evds_catalog.parquet"
DEFAULT_EMBEDDING_CATALOG = BACKEND_DIR.parent / "data" / "gold" / "series_embeddings.parquet"


def _normalize_series_code(code: str) -> str:
    """Strips any source prefix, e.g. 'EVDS:TP.DK.USD.A.YTL' -> 'TP.DK.USD.A.YTL'."""
    clean = code.strip()
    if clean.startswith("EVDS:"):
        clean = clean.split(":", 1)[1]
    return clean


def load_evds_series(
    series_code: str,
    start_date: str = "01-01-2021",
    end_date: str = "01-06-2026",
    add_to_silver: bool = True,
    client: Optional[EvdsClient] = None,
    bronze_dir: Optional[Path] = None,
    silver_dir: Optional[Path] = None,
    silver_db_path: Optional[Path] = None,
    aligned_db_path: Optional[Path] = None,
    metadata_raw_path: Optional[Path] = None,
    embedding_catalog_path: Optional[Path] = None,
    context: Literal["batch", "live"] = "batch",
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
        aligned_db_path: Optional override for monthly aligned.duckdb path.
        metadata_raw_path: Optional override for metadata_raw.json path.

    Returns:
        Summary dict containing series info, row counts, preview, and silver status.
    """
    if context not in {"batch", "live"}:
        raise ValueError(f"Unsupported EVDS loader context: {context!r}")

    code = _normalize_series_code(series_code)
    series_id = f"EVDS:{code}"

    b_dir = bronze_dir or DEFAULT_BRONZE_DIR
    s_dir = silver_dir or DEFAULT_SILVER_DIR
    db_path = silver_db_path or DEFAULT_SILVER_DB
    aligned_path = (
        aligned_db_path
        if aligned_db_path is not None
        else (DEFAULT_ALIGNED_DB if silver_db_path is None else None)
    )
    meta_path = metadata_raw_path or DEFAULT_METADATA_RAW
    embedding_path = embedding_catalog_path or DEFAULT_EMBEDDING_CATALOG

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
    nature = str(dim_row.get("nature") or "unclassified")
    nature_reviewed = bool(dim_row.get("nature_reviewed", False))
    alignment_override = dim_row.get("alignment_override")
    pending_review = add_to_silver and nature == "unclassified"

    if pending_review and context == "batch":
        raise ValueError(
            f"Series {series_id!r} has unclassified series nature; "
            "cannot add it to canonical Silver."
        )

    if pending_review and context == "live":
        logger.info(
            "Live EVDS series %s is unclassified; it will be stored with "
            "nature_reviewed=False and must not enter alignment or Gold.",
            series_id,
        )

    # Persist transformed EVDS Silver through the transformer boundary
    upsert_single_series_to_silver_parquet(
        series_id,
        raw_obs_rows,
        dim_row,
        silver_dir=s_dir,
    )

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
        nature_reviewed=nature_reviewed,
        alignment_override=alignment_override,
    )
    canonical_meta_dict = meta_model.model_dump()

    # 5. Insert into silver.duckdb if requested
    added_to_silver = False
    if add_to_silver and db_path.exists():
        canonical_obs_df = pd.DataFrame(canonical_obs_rows)
        # Ensure dims is string JSON for DuckDB JSON column
        canonical_obs_df["dims"] = canonical_obs_df["dims"].map(
            lambda d: json.dumps(d, ensure_ascii=False)
        )
        # Safeguard: deduplicate by PK (series_id, date, dims) to avoid constraint violation
        canonical_obs_df = canonical_obs_df.drop_duplicates(
            subset=["series_id", "date", "dims"], keep="last"
        )
        canonical_meta_df = pd.DataFrame([canonical_meta_dict])

        con = duckdb.connect(str(db_path))
        try:
            con.execute("BEGIN TRANSACTION")
            # Idempotently delete existing records
            con.execute("DELETE FROM observations WHERE series_id = ?", [series_id])
            con.execute("DELETE FROM series_metadata WHERE series_id = ?", [series_id])

            con.register("_new_canonical_obs", canonical_obs_df)
            con.execute(
                """
                INSERT INTO observations (
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
                )
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
                INSERT INTO series_metadata (
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
                )
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
                    CAST(nature_reviewed AS BOOLEAN),
                    CAST(alignment_override AS VARCHAR)
                FROM _new_canonical_meta
                """
            )
            con.execute("COMMIT")
            added_to_silver = True
            logger.info(
                f"Successfully inserted {len(canonical_obs_rows)} rows into {db_path.name}"
            )
        except Exception:
            con.execute("ROLLBACK")
            raise
        finally:
            con.close()

    # 6. Update monthly aligned layer when series semantics are known.
    added_to_aligned = False
    if (
        add_to_silver
        and added_to_silver
        and not pending_review
        and aligned_path is not None
    ):
        if not aligned_path.exists():
            raise FileNotFoundError(
                f"Aligned database not found: {aligned_path}"
            )

        alignment_obs = pd.DataFrame(canonical_obs_rows)
        alignment_meta = pd.DataFrame([canonical_meta_dict])
        policies = build_alignment_policies(alignment_meta)
        aligned_rows = align_to_monthly(
            alignment_obs,
            alignment_meta,
            policies,
            quarterly_policy="sparse",
        )

        try:
            upsert_single_series_to_aligned_duckdb(
                db_path=aligned_path,
                series_id=series_id,
                aligned=aligned_rows,
                metadata=alignment_meta,
            )
            added_to_aligned = True
        except Exception:
            logger.critical(
                "Canonical Silver was updated for %s but aligned update failed; "
                "cross-layer inconsistency is possible and requires repair/rebuild.",
                series_id,
                exc_info=True,
            )
            raise

    # 7. Best-effort semantic catalog refresh.
    # Missing embedding artifacts are intentionally not bootstrapped here;
    # series_catalog_search can fall back to Silver metadata.
    embedding_catalog_updated = False
    if add_to_silver and added_to_silver:
        try:
            embedding_catalog_updated = _upsert_embedding_catalog_series(
                series_id=series_id,
                silver_db_path=db_path,
                metadata_raw_path=meta_path,
                output_path=embedding_path,
            )
        except Exception:
            logger.warning(
                "Silver data was updated for %s but incremental embedding "
                "catalog refresh failed; metadata fallback remains available.",
                series_id,
                exc_info=True,
            )

    # 8. Build preview (all canonical observations)
    sorted_obs = sorted(canonical_obs_rows, key=lambda x: x["date"])
    preview = [
        {"date": str(o["date"]), "value": o["value"]}
        for o in sorted_obs
    ]

    return {
        "status": "pending_review" if pending_review else "success",
        "message": (
            "Bu seri sisteme yeni ekleniyor, seri sınıflandırması inceleme bekliyor. "
            "Kesin analiz için sınıflandırma tamamlandıktan sonra tekrar deneyin."
            if pending_review
            else None
        ),
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
        "added_to_aligned": added_to_aligned,
        "embedding_catalog_updated": embedding_catalog_updated,
        "preview": preview,
    }
