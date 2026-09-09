"""EVDS series ingestion pipeline for the Bronze Layer."""
import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional, Union
import yaml

from app.modules.evds.catalog_store import update_series_status
from app.modules.evds.client import EvdsClient

logger = logging.getLogger(__name__)


def load_manifest(manifest_path: Union[str, Path]) -> Dict[str, Any]:
    """Loads and validates the series manifest YAML file.

    Args:
        manifest_path: Path to the series_manifest.yaml file.

    Returns:
        Parsed YAML content dictionary.

    Raises:
        FileNotFoundError: If the manifest file does not exist.
        ValueError: If YAML is malformed, missing 'series', or invalid.
    """
    path = Path(manifest_path)
    if not path.exists():
        raise FileNotFoundError(f"Series manifest file not found: {manifest_path}")

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except Exception as e:
        raise ValueError(f"Failed to parse series manifest YAML: {e}") from e

    if not isinstance(data, dict):
        raise ValueError(f"Manifest root must be a dictionary, got {type(data)}")

    series_list = data.get("series")
    if not isinstance(series_list, list) or len(series_list) == 0:
        raise ValueError("Manifest must contain a non-empty 'series' list.")

    # Validate each series has required 'code' field
    for idx, item in enumerate(series_list):
        if not isinstance(item, dict) or "code" not in item or not item["code"]:
            raise ValueError(f"Series entry #{idx + 1} is missing the required 'code' attribute.")

    return data


def ingest_series(
    manifest_path: Union[str, Path],
    output_dir: Union[str, Path],
    client: Optional[EvdsClient] = None,
) -> Dict[str, Any]:
    """Downloads all series defined in the manifest into the Bronze Layer raw JSON storage.

    Implements idempotency: If the target file already exists and is not empty (>0 bytes),
    API download is skipped.

    Args:
        manifest_path: Path to the series manifest YAML file.
        output_dir: Target directory for raw JSON files (e.g., data/bronze/evds).
        client: Optional EvdsClient instance. If not provided, a default one is instantiated.

    Returns:
        Summary dict containing counts of processed, fetched, and skipped series.
    """
    manifest_data = load_manifest(manifest_path)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    if client is None:
        client = EvdsClient()

    default_start_date = manifest_data.get("default_start_date", "01-01-2021")
    default_end_date = manifest_data.get("default_end_date", "01-06-2026")
    series_list = manifest_data["series"]

    fetched_count = 0
    skipped_count = 0
    failed_count = 0

    for item in series_list:
        code = item["code"]
        start_date = item.get("start_date") or default_start_date
        end_date = item.get("end_date") or default_end_date
        target_file = output_path / f"{code}.json"

        # BR-04: Idempotency check - skip if exists and non-empty
        if target_file.exists() and target_file.stat().st_size > 0:
            logger.info(f"[SKIP] Series {code} already exists at {target_file} (size: {target_file.stat().st_size} bytes)")
            skipped_count += 1
            continue

        # Fetch raw data from EVDS with strict validation
        logger.info(f"Fetching series {code} from EVDS ({start_date} to {end_date})...")
        try:
            raw_data = client.get_data(
                series_code=code,
                start_date=start_date,
                end_date=end_date,
                raw=True,
            )

            # Strict check: reject None, empty lists or invalid payloads
            if raw_data is None or not isinstance(raw_data, (list, dict)) or len(raw_data) == 0:
                raise ValueError(f"EVDS returned empty/null payload for series '{code}': {raw_data}")

            # Write raw JSON to bronze storage
            with open(target_file, "w", encoding="utf-8") as f:
                json.dump(raw_data, f, ensure_ascii=False, indent=2)

            logger.info(f"[FETCH] Series {code} successfully saved to {target_file} ({len(raw_data)} records)")
            fetched_count += 1

            # Update catalog store status (SUCCESS)
            update_series_status(
                catalog_path=output_path / "evds_catalog.parquet",
                series_code=code,
                is_ingested=True,
                fetch_status="SUCCESS",
            )
        except Exception as err:
            logger.error(f"[ERROR] Failed to ingest series {code}: {err}")
            failed_count += 1
            # Ensure failed target file is removed if empty/null
            if target_file.exists() and target_file.stat().st_size <= 10:
                target_file.unlink(missing_ok=True)

            # Update catalog store as FAILED
            update_series_status(
                catalog_path=output_path / "evds_catalog.parquet",
                series_code=code,
                is_ingested=False,
                fetch_status="FAILED",
            )

    return {
        "total": len(series_list),
        "fetched": fetched_count,
        "skipped": skipped_count,
        "failed": failed_count,
    }
