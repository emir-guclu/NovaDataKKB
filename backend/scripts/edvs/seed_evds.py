"""CLI Trigger Script: Seeds EVDS Bronze Layer from series_manifest.yaml."""
import logging
import sys
from pathlib import Path

# Add backend directory to sys.path so app modules can be imported directly
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

# Optional dotenv loading if installed
try:
    from dotenv import load_dotenv

    # Try loading from project root or backend dir
    env_path = backend_dir.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
    else:
        load_dotenv(backend_dir / ".env")
except ImportError:
    pass

from app.modules.evds.ingestion import ingest_series

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("seed_evds")


def main() -> None:
    """Main execution entrypoint for EVDS seed script."""
    manifest_path = backend_dir / "app" / "modules" / "evds" / "series_manifest.yaml"
    output_dir = backend_dir.parent / "data" / "bronze" / "evds"

    logger.info("Starting EVDS Bronze layer ingestion...")
    logger.info(f"Manifest path: {manifest_path}")
    logger.info(f"Output directory: {output_dir}")

    try:
        summary = ingest_series(
            manifest_path=manifest_path,
            output_dir=output_dir,
        )
        logger.info(
            f"EVDS Ingestion completed successfully! Total: {summary['total']}, "
            f"Fetched: {summary['fetched']}, Skipped: {summary['skipped']}, Failed: {summary['failed']}"
        )
        sys.exit(0)
    except Exception as err:
        logger.error(f"EVDS Ingestion failed: {err}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
