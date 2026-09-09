"""EVDS Catalog discovery pipeline for scanning categories and series metadata."""
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
import pandas as pd

from app.modules.evds.catalog_store import save_catalog
from app.modules.evds.client import EvdsClient

logger = logging.getLogger(__name__)

REQUIRED_CATALOG_COLUMNS = [
    "category_id",
    "category_name",
    "datagroup_id",
    "datagroup_name",
    "series_code",
    "series_name",
    "frequency",
    "is_ingested",
    "fetch_status",
    "last_ingested_at",
]


def _to_record_list(data: Any) -> List[Dict[str, Any]]:
    """Normalizes API response into a list of dictionaries."""
    if data is None:
        return []
    if isinstance(data, pd.DataFrame):
        return data.to_dict(orient="records")
    if isinstance(data, list):
        return [item if isinstance(item, dict) else dict(item) for item in data]
    if isinstance(data, dict):
        return [data]
    return []


def discover_all(
    client: Optional[EvdsClient] = None,
    output_path: Optional[Union[str, Path]] = None,
) -> pd.DataFrame:
    """Discovers all EVDS categories, datagroups, and series, returning a catalog DataFrame.

    Scans get_main_categories -> get_sub_categories -> get_series to build a complete
    metadata snapshot, initializes ingestion tracking columns, and optionally saves
    the resulting DataFrame to a Parquet file.

    Args:
        client: Optional EvdsClient instance. If not provided, an instance is created.
        output_path: Optional target path to save the evds_catalog.parquet file.

    Returns:
        pd.DataFrame containing all discovered series with metadata.
    """
    if client is None:
        client = EvdsClient()

    logger.info("Starting EVDS catalog discovery...")
    categories_raw = client.get_main_categories()
    categories = _to_record_list(categories_raw)

    rows: List[Dict[str, Any]] = []

    for cat in categories:
        cat_id = cat.get("CATEGORY_ID") or cat.get("category_id") or cat.get("id")
        cat_name = cat.get("TOPIC_TITLE_TR") or cat.get("CATEGORY_NAME") or cat.get("category_name") or cat.get("name")

        if cat_id is None:
            continue

        logger.info(f"Scanning category {cat_id} ({cat_name})... Current total series: {len(rows)}")
        try:
            sub_cats_raw = client.get_sub_categories(cat_id)
            sub_categories = _to_record_list(sub_cats_raw)
        except Exception as e:
            logger.warning(f"Failed to fetch subcategories for category {cat_id}: {e}")
            continue

        for sub in sub_categories:
            dg_id = sub.get("DATAGROUP_CODE") or sub.get("datagroup_id") or sub.get("DATAGROUP_ID") or sub.get("code")
            dg_name = sub.get("DATAGROUP_NAME") or sub.get("datagroup_name") or sub.get("name")

            if dg_id is None:
                continue

            logger.debug(f"Scanning series for datagroup {dg_id} ({dg_name})...")
            try:
                series_raw = client.get_series(dg_id)
                series_list = _to_record_list(series_raw)
            except Exception as e:
                logger.warning(f"Could not fetch series for datagroup {dg_id}: {e}")
                continue

            for s in series_list:
                series_code = s.get("SERIE_CODE") or s.get("series_code") or s.get("code")
                series_name = s.get("SERIE_NAME") or s.get("series_name") or s.get("name")
                frequency = s.get("FREQUENCY_STR") or s.get("frequency") or s.get("DEFAULT_FREQUENCY")

                if series_code is None:
                    continue

                rows.append({
                    "category_id": cat_id,
                    "category_name": cat_name,
                    "datagroup_id": dg_id,
                    "datagroup_name": dg_name,
                    "series_code": series_code,
                    "series_name": series_name,
                    "frequency": frequency,
                    "is_ingested": False,
                    "fetch_status": None,
                    "last_ingested_at": None,
                })

    df = pd.DataFrame(rows, columns=REQUIRED_CATALOG_COLUMNS)
    df["is_ingested"] = df["is_ingested"].astype(bool)

    logger.info(f"Discovery complete: found {len(df)} series across {len(categories)} categories.")

    if output_path is not None:
        save_catalog(df, output_path)

    return df
