"""CLI Trigger Script: Seeds EVDS Catalog (Discovery) to Bronze Layer."""
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

from app.modules.evds.catalog import discover_all

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("seed_catalog")


def main() -> None:
    """Main execution entrypoint for EVDS catalog discovery script."""
    output_path = backend_dir.parent / "data" / "bronze" / "evds" / "evds_catalog.parquet"

    logger.info("Starting EVDS Catalog Discovery...")
    logger.info(f"Target catalog path: {output_path}")

    try:
        df = discover_all(output_path=output_path)
        logger.info(
            f"EVDS Catalog Discovery completed successfully! Total series discovered: {len(df)}"
        )
        sys.exit(0)
    except Exception as err:
        logger.error(f"EVDS Catalog Discovery failed: {err}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
