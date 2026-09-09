"""EVDS Metadata Ingestion & Synchronization Module.

Fetches and synchronizes rich TCMB official metadata (NOTE, BIRIMI, TAG, FREQUENCY_STR, etc.)
for all series defined in series_manifest.yaml and saves them into data/bronze/evds/metadata_raw.json.

Design Principles:
- Idempotent: If all manifest series already exist in metadata_raw.json, network calls are skipped.
- Incremental: When new series are added to manifest, only their datagroups/categories are queried.
- Atomic: Writes to temporary file before atomic rename to prevent corruption.
- Single Source of Truth: Captures official CBRT descriptions, units, and tags directly from API.
"""

import json
import logging
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Union

import pandas as pd
import yaml
from dotenv import load_dotenv

from app.modules.evds.catalog_store import load_catalog
from app.modules.evds.client import EvdsClient

# Automatically load .env if present
load_dotenv()

logger = logging.getLogger(__name__)

DEFAULT_MANIFEST_PATH = Path("backend/app/modules/evds/series_manifest.yaml")
DEFAULT_CATALOG_PATH = Path("data/bronze/evds/evds_catalog.parquet")
DEFAULT_METADATA_OUTPUT_PATH = Path("data/bronze/evds/metadata_raw.json")


def clean_text(val: Optional[str]) -> Optional[str]:
    """Cleans multiple spaces and whitespace from string."""
    if val is None:
        return None
    val = str(val).strip()
    return re.sub(r"\s+", " ", val) if val else None


def load_manifest_series(manifest_path: Union[str, Path] = DEFAULT_MANIFEST_PATH) -> List[Dict[str, Any]]:
    """Loads series list from YAML manifest."""
    path = Path(manifest_path)
    if not path.exists():
        raise FileNotFoundError(f"Manifest file not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    return data.get("series", [])


def load_existing_metadata(metadata_path: Union[str, Path] = DEFAULT_METADATA_OUTPUT_PATH) -> Dict[str, Any]:
    """Loads existing metadata_raw.json if present, returning a dictionary keyed by series_code."""
    path = Path(metadata_path)
    if not path.exists():
        return {}

    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        logger.warning(f"Could not read existing metadata file {path} ({exc}). Will rebuild.")
        return {}


def save_metadata_atomic(
    metadata_dict: Dict[str, Any],
    metadata_path: Union[str, Path] = DEFAULT_METADATA_OUTPUT_PATH,
) -> Path:
    """Atomically saves metadata dictionary to JSON using a temp file and replace."""
    path = Path(metadata_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False, encoding="utf-8", suffix=".tmp") as tf:
        json.dump(metadata_dict, tf, ensure_ascii=False, indent=2)
        temp_name = tf.name

    os.replace(temp_name, path)
    logger.info(f"Successfully saved {len(metadata_dict)} series metadata to {path}")
    return path


def sync_metadata(
    manifest_path: Union[str, Path] = DEFAULT_MANIFEST_PATH,
    catalog_path: Union[str, Path] = DEFAULT_CATALOG_PATH,
    output_path: Union[str, Path] = DEFAULT_METADATA_OUTPUT_PATH,
    client: Optional[EvdsClient] = None,
    force: bool = False,
) -> Dict[str, Any]:
    """Synchronizes rich metadata for manifest series into metadata_raw.json.

    Args:
        manifest_path: Path to series_manifest.yaml.
        catalog_path: Path to evds_catalog.parquet.
        output_path: Target path for data/bronze/evds/metadata_raw.json.
        client: Optional EvdsClient instance.
        force: If True, re-fetches metadata for all series ignoring existing JSON.

    Returns:
        The updated dictionary of series metadata.
    """
    manifest_series = load_manifest_series(manifest_path)
    if not manifest_series:
        logger.warning("Manifest has no series defined.")
        return {}

    manifest_codes = [s["code"] for s in manifest_series if "code" in s]
    existing_meta = {} if force else load_existing_metadata(output_path)

    missing_codes = [code for code in manifest_codes if code not in existing_meta]
    if not missing_codes:
        logger.info(f"[SKIP] All {len(manifest_codes)} series already exist in {output_path}. No network calls needed.")
        return existing_meta

    logger.info(f"Found {len(missing_codes)} missing series to fetch metadata: {missing_codes}")

    # Load local catalog to resolve category_id and datagroup_id
    catalog_df = load_catalog(catalog_path)
    catalog_subset = catalog_df[catalog_df["series_code"].isin(missing_codes)]

    if catalog_subset.empty:
        raise ValueError(f"None of the missing series {missing_codes} were found in catalog {catalog_path}")

    # Group by category_id and datagroup_id
    needed_categories: Set[Any] = set(catalog_subset["category_id"].dropna().unique())
    needed_datagroups: Set[str] = set(catalog_subset["datagroup_id"].dropna().unique())

    if client is None:
        client = EvdsClient()

    # Step 1: Fetch all datagroup metadata in one single call to obtain NOTE, BIRIMI, METADATA_LINK
    logger.info("Fetching all datagroups metadata from EVDS for official NOTE and BIRIMI...")
    all_sub_cats = client.get_sub_categories("", raw=True)
    datagroup_meta: Dict[str, Dict[str, Any]] = {}
    if isinstance(all_sub_cats, list):
        for sc in all_sub_cats:
            dg_code = sc.get("DATAGROUP_CODE")
            if dg_code:
                datagroup_meta[dg_code] = {
                    "DATAGROUP_CODE": dg_code,
                    "CATEGORY_ID": sc.get("CATEGORY_ID"),
                    "DATAGROUP_NAME": clean_text(sc.get("DATAGROUP_NAME")),
                    "DATAGROUP_NAME_ENG": clean_text(sc.get("DATAGROUP_NAME_ENG")),
                    "FREQUENCY_STR": clean_text(sc.get("FREQUENCY_STR")),
                    "NOTE": clean_text(sc.get("NOTE")),
                    "NOTE_ENG": clean_text(sc.get("NOTE_ENG")),
                    "BIRIMI": clean_text(sc.get("BIRIMI")),
                    "BIRIMI_EN": clean_text(sc.get("BIRIMI_EN")),
                    "METADATA_LINK": sc.get("METADATA_LINK"),
                }

    # Step 2: Query get_series for needed datagroups (to obtain SERIE_NAME, TAG, FREQUENCY_STR)
    series_meta: Dict[str, Dict[str, Any]] = {}
    for dg_code in needed_datagroups:
        try:
            logger.info(f"Fetching series details for datagroup {dg_code} (TAG, SERIE_NAME, FREQUENCY_STR)...")
            s_res = client.get_series(dg_code, raw=True)
            if isinstance(s_res, list):
                for s in s_res:
                    s_code = s.get("SERIE_CODE")
                    if s_code and s_code in missing_codes:
                        series_meta[s_code] = s
        except Exception as exc:
            logger.error(f"Error fetching series for datagroup {dg_code}: {exc}")

    # Step 3: Combine catalog + datagroup_meta + series_meta for each missing code
    for _, row in catalog_subset.iterrows():
        s_code = row["series_code"]
        dg_id = row.get("datagroup_id")
        cat_id = row.get("category_id")

        dg_info = datagroup_meta.get(dg_id, {})
        s_info = series_meta.get(s_code, {})

        # Resolve official fields
        serie_name = clean_text(s_info.get("SERIE_NAME") or row.get("series_name"))
        serie_name_eng = clean_text(s_info.get("SERIE_NAME_ENG"))
        freq_str = clean_text(s_info.get("FREQUENCY_STR") or dg_info.get("FREQUENCY_STR"))
        note = dg_info.get("NOTE")
        unit = dg_info.get("BIRIMI")
        tag = clean_text(s_info.get("TAG"))
        tag_list = [t.strip() for t in tag.split(",") if t.strip()] if tag else []

        record = {
            "SERIE_CODE": s_code,
            "SERIE_NAME": serie_name,
            "SERIE_NAME_ENG": serie_name_eng,
            "DATAGROUP_CODE": dg_id,
            "DATAGROUP_NAME": dg_info.get("DATAGROUP_NAME") or row.get("datagroup_name"),
            "CATEGORY_ID": cat_id,
            "CATEGORY_NAME": clean_text(row.get("category_name")),
            "FREQUENCY_STR": freq_str,
            "DEFAULT_AGG_METHOD_STR": clean_text(s_info.get("DEFAULT_AGG_METHOD_STR")),
            "START_DATE": s_info.get("START_DATE"),
            "END_DATE": s_info.get("END_DATE"),
            "BIRIMI": unit,
            "BIRIMI_EN": dg_info.get("BIRIMI_EN"),
            "NOTE": note,
            "NOTE_ENG": dg_info.get("NOTE_ENG"),
            "TAG": tag_list,
            "METADATA_LINK": dg_info.get("METADATA_LINK"),
        }
        existing_meta[s_code] = record

    # Step 4: Atomic save
    save_metadata_atomic(existing_meta, output_path)
    return existing_meta


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    sync_metadata()
