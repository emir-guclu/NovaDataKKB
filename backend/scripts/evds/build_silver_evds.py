"""CLI Trigger Script: Runs EVDS Silver Pipeline (Metadata Sync & Parquet Transformation)."""
import argparse
import logging
import sys
from pathlib import Path

# Add backend directory to sys.path so app modules can be imported directly
backend_dir = Path(__file__).resolve().parent.parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

# Optional dotenv loading
try:
    from dotenv import load_dotenv

    env_path = backend_dir.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
    else:
        load_dotenv(backend_dir / ".env")
except ImportError:
    pass

from app.modules.evds.metadata import (
    load_manifest_series,
    sync_metadata,
)
from app.modules.evds.transformer import transform_silver_evds

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("build_silver_evds")


def main() -> None:
    """Main execution entrypoint for EVDS Silver pipeline script."""
    parser = argparse.ArgumentParser(description="EVDS Silver Pipeline: Metadata Sync & Parquet Transformation")
    parser.add_argument(
        "--full-refresh",
        action="store_true",
        help="Rebuild observations.parquet and series_metadata.parquet from scratch",
    )
    parser.add_argument(
        "--force-metadata",
        action="store_true",
        help="Force re-fetching metadata from TCMB API even if metadata_raw.json exists",
    )
    args = parser.parse_args()

    project_root = backend_dir.parent
    manifest_path = backend_dir / "app" / "modules" / "evds" / "series_manifest.yaml"
    catalog_path = project_root / "data" / "bronze" / "evds" / "evds_catalog.parquet"
    metadata_json_path = project_root / "data" / "bronze" / "evds" / "metadata_raw.json"
    bronze_dir = project_root / "data" / "bronze" / "evds"
    silver_dir = project_root / "data" / "silver" / "evds"

    logger.info("=== STEP 1: Synchronizing EVDS Metadata ===")
    sync_metadata(
        manifest_path=manifest_path,
        catalog_path=catalog_path,
        output_path=metadata_json_path,
        force=args.force_metadata,
    )

    logger.info("=== STEP 2: Transforming Bronze to Silver Parquet ===")
    obs_path, meta_path = transform_silver_evds(
        bronze_dir=bronze_dir,
        metadata_json_path=metadata_json_path,
        silver_dir=silver_dir,
        manifest_path=manifest_path,
        full_refresh=args.full_refresh,
    )

    expected_series = load_manifest_series(manifest_path)

    expected_codes = {
        str(item["code"])
        for item in expected_series
        if isinstance(item, dict) and item.get("code")
    }

    if not expected_codes:
        raise RuntimeError(
            "No EVDS series codes could be extracted from series_manifest.yaml"
        )

    available_bronze_codes = {
        file_path.stem
        for file_path in bronze_dir.glob("*.json")
        if file_path.name != "metadata_raw.json"
    }

    available_expected = (
        expected_codes & available_bronze_codes
    )

    missing_bronze = (
        expected_codes - available_bronze_codes
    )

    coverage_pct = (
        100.0 * len(available_expected) / len(expected_codes)
    )

    logger.info("=== EVDS BRONZE COVERAGE ===")
    logger.info(
        "Expected manifest series: %d",
        len(expected_codes),
    )
    logger.info(
        "Available Bronze series: %d",
        len(available_expected),
    )
    logger.info(
        "Missing Bronze series: %d",
        len(missing_bronze),
    )
    logger.info(
        "Coverage: %.2f%%",
        coverage_pct,
    )

    logger.info("=== SILVER PIPELINE COMPLETED SUCCESSFULLY ===")
    logger.info(f"Observations Parquet: {obs_path}")
    logger.info(f"Series Metadata Parquet: {meta_path}")


if __name__ == "__main__":
    main()
