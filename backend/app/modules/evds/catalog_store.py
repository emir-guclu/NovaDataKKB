"""EVDS Parquet Catalog storage and synchronization operations."""
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Union
import pandas as pd

import os
import uuid

logger = logging.getLogger(__name__)


def load_catalog(catalog_path: Union[str, Path]) -> pd.DataFrame:
    """Loads the EVDS catalog parquet file into a pandas DataFrame.

    Args:
        catalog_path: Path to the evds_catalog.parquet file.

    Returns:
        pd.DataFrame containing the catalog data.

    Raises:
        FileNotFoundError: If the catalog file does not exist.
    """
    path = Path(catalog_path)
    if not path.exists():
        raise FileNotFoundError(f"Catalog file not found at: {catalog_path}")
    return pd.read_parquet(path)


def save_catalog(df: pd.DataFrame, catalog_path: Union[str, Path]) -> None:
    """Saves the EVDS catalog DataFrame to a parquet file using an atomic write pattern.

    Writes to a temporary file in the same directory and atomically replaces the target
    to prevent file corruption and race conditions during concurrent access (W-01).

    Args:
        df: Catalog pandas DataFrame to save.
        catalog_path: Path where the parquet file should be saved.
    """
    path = Path(catalog_path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(f".tmp_{os.getpid()}_{uuid.uuid4().hex[:8]}.parquet")
    try:
        df.to_parquet(temp_path, index=False)
        temp_path.replace(path)
    finally:
        if temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass
    logger.info(f"Catalog saved to {path} ({len(df)} rows)")


def update_series_status(
    catalog_path: Union[str, Path],
    series_code: str,
    is_ingested: bool = True,
    fetch_status: Optional[str] = "SUCCESS",
    last_ingested_at: Optional[Union[str, datetime]] = None,
) -> bool:
    """Updates the ingestion status and timestamp of a series in the parquet catalog.

    Args:
        catalog_path: Path to the evds_catalog.parquet file.
        series_code: Code of the series to update (e.g. 'TP.KTF10').
        is_ingested: Boolean flag indicating if the series has been ingested.
        fetch_status: Status string (e.g., 'SUCCESS', 'FAILED', 'PENDING').
        last_ingested_at: Optional timestamp; defaults to current UTC time.

    Returns:
        True if the series was found and updated, False if series not in catalog or catalog missing.
    """
    path = Path(catalog_path)
    if not path.exists():
        logger.warning(f"Catalog file does not exist at {path}, cannot update series status.")
        return False

    try:
        df = pd.read_parquet(path)
    except Exception as e:
        logger.error(f"Failed to read catalog at {path}: {e}")
        return False

    if "series_code" not in df.columns:
        logger.warning(f"Catalog at {path} does not have 'series_code' column.")
        return False

    mask = df["series_code"] == series_code
    if not mask.any():
        logger.warning(f"Series '{series_code}' not found in catalog {path}.")
        return False

    if last_ingested_at is None:
        last_ingested_at = datetime.now(timezone.utc).isoformat()

    df.loc[mask, "is_ingested"] = is_ingested
    df.loc[mask, "fetch_status"] = fetch_status
    df.loc[mask, "last_ingested_at"] = str(last_ingested_at)

    save_catalog(df, path)
    logger.info(
        f"Updated status for series '{series_code}' in catalog: is_ingested={is_ingested}, status={fetch_status}"
    )
    return True
