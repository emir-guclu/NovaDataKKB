"""Unified EVDS Bronze Layer Orchestrator Script.

Builds the entire EVDS Bronze layer end-to-end:
1. Discovers and caches the full EVDS catalog (evds_catalog.parquet)
2. Ingests all series from series_manifest.yaml as raw JSON files
3. Synchronizes rich CBRT metadata into metadata_raw.json

Usage:
    python backend/scripts/evds/build_bronze_evds.py
    python backend/scripts/evds/build_bronze_evds.py --full-refresh
    python backend/scripts/evds/build_bronze_evds.py --skip-catalog
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Add backend directory to sys.path
BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Load .env
try:
    from dotenv import load_dotenv

    env_path = BACKEND_DIR.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
    else:
        load_dotenv(BACKEND_DIR / ".env")
except ImportError:
    pass

from app.modules.evds.catalog import discover_all
from app.modules.evds.ingestion import ingest_series
from app.modules.evds.metadata import sync_metadata

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("build_bronze_evds")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Unified EVDS Bronze Layer Orchestrator"
    )
    parser.add_argument(
        "--full-refresh",
        action="store_true",
        help="Force re-discovery of catalog and re-downloading all Bronze JSONs",
    )
    parser.add_argument(
        "--skip-catalog",
        action="store_true",
        help="Skip catalog discovery and only ingest manifest series",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    root_dir = BACKEND_DIR.parent
    bronze_dir = root_dir / "data" / "bronze" / "evds"
    bronze_dir.mkdir(parents=True, exist_ok=True)

    catalog_path = bronze_dir / "evds_catalog.parquet"
    manifest_path = (
        BACKEND_DIR / "app" / "modules" / "evds" / "series_manifest.yaml"
    )
    metadata_raw_path = bronze_dir / "metadata_raw.json"

    logger.info("=" * 70)
    logger.info("EVDS BRONZE LAYER BUILD STARTED")
    logger.info("=" * 70)
    logger.info(f"Target Directory : {bronze_dir}")
    logger.info(f"Manifest Path    : {manifest_path}")
    logger.info(f"Full Refresh     : {args.full_refresh}")

    # Step 1: Catalog Discovery
    if not args.skip_catalog:
        if catalog_path.exists() and not args.full_refresh:
            logger.info(
                f"[SKIP] Catalog already exists at {catalog_path} "
                f"({catalog_path.stat().st_size:,} bytes). Use --full-refresh to re-discover."
            )
        else:
            logger.info("--- Step 1: Discovering EVDS Catalog ---")
            try:
                catalog_df = discover_all(output_path=catalog_path)
                logger.info(
                    f"Catalog discovery completed with {len(catalog_df):,} series."
                )
            except Exception as err:
                logger.warning(
                    f"Catalog discovery warning/error: {err}. "
                    "Proceeding with existing manifest if available..."
                )
    else:
        logger.info("[SKIP] Catalog discovery skipped via --skip-catalog.")

    # Step 2: Ingest Raw Series JSONs
    logger.info("--- Step 2: Ingesting Manifest Series JSONs ---")
    if args.full_refresh:
        # If full refresh, remove existing raw series JSONs (preserve catalog and metadata_raw)
        for json_file in bronze_dir.glob("*.json"):
            if json_file.name != "metadata_raw.json":
                try:
                    json_file.unlink()
                except OSError:
                    pass

    ingest_summary = ingest_series(
        manifest_path=manifest_path,
        output_dir=bronze_dir,
    )
    logger.info(
        f"Ingestion Result: Total={ingest_summary['total']}, "
        f"Fetched={ingest_summary['fetched']}, "
        f"Skipped={ingest_summary['skipped']}, "
        f"Failed={ingest_summary['failed']}"
    )

    # Step 3: Synchronize Official Metadata
    logger.info("--- Step 3: Synchronizing Official CBRT Metadata ---")
    try:
        sync_meta_summary = sync_metadata(
            manifest_path=manifest_path,
            catalog_path=catalog_path if catalog_path.exists() else None,
            output_path=metadata_raw_path,
        )
        logger.info(
            f"Metadata Sync Result: Total Ingested={sync_meta_summary.get('total_ingested', 0)}, "
            f"Skipped={sync_meta_summary.get('skipped_existing', 0)}"
        )
    except Exception as err:
        logger.error(f"Metadata sync encountered error: {err}")

    # Summary
    json_count = len(
        [
            f
            for f in bronze_dir.glob("*.json")
            if f.name != "metadata_raw.json"
        ]
    )

    logger.info("=" * 70)
    logger.info("EVDS BRONZE BUILD COMPLETE")
    logger.info("=" * 70)
    logger.info(f"Bronze JSON Files Present : {json_count}")
    logger.info(f"Catalog Exists            : {catalog_path.exists()}")
    logger.info(f"Raw Metadata Exists       : {metadata_raw_path.exists()}")
    logger.info("=" * 70)


if __name__ == "__main__":
    main()
