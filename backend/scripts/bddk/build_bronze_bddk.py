"""Unified BDDK Bronze Layer Orchestrator Script.

Manages and builds the 3 BDDK Bronze datasets:
1. Weekly Bulletin  -> data/bronze/bddk/weekly/bddk_weekly_all_2021_2026.csv
2. Monthly Bulletin -> data/bronze/bddk/monthly/bddk_monthly_all_2021_2026_precise.csv
3. FinTürk Bulletin -> data/bronze/bddk/finturk/bddk_finturk_all_2021_2026.csv

Design:
- Idempotent by default: Checks existing CSV files, reports size and row counts.
- If a file exists, skips scraping to avoid redundant heavy HTTP requests.
- Use --full-refresh to force re-scraping all 3 sources.
- Use --only-weekly, --only-monthly, or --only-finturk to scrape specific targets.

Usage:
    python backend/scripts/bddk/build_bronze_bddk.py
    python backend/scripts/bddk/build_bronze_bddk.py --full-refresh
    python backend/scripts/bddk/build_bronze_bddk.py --only-weekly
"""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys
from pathlib import Path

# Add backend directory to sys.path
BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("build_bronze_bddk")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Unified BDDK Bronze Layer Orchestrator"
    )
    parser.add_argument(
        "--full-refresh",
        action="store_true",
        help="Force re-scraping and downloading all BDDK Bronze datasets",
    )
    parser.add_argument(
        "--only-weekly",
        action="store_true",
        help="Scrape only BDDK Weekly Bulletin",
    )
    parser.add_argument(
        "--only-monthly",
        action="store_true",
        help="Scrape only BDDK Monthly Bulletin",
    )
    parser.add_argument(
        "--only-finturk",
        action="store_true",
        help="Scrape only BDDK FinTürk Bulletin",
    )
    return parser.parse_args()


def get_csv_stats(file_path: Path) -> tuple[bool, int, float]:
    """Returns (exists, line_count, size_mb)."""
    if not file_path.exists() or file_path.stat().st_size == 0:
        return False, 0, 0.0

    size_mb = file_path.stat().st_size / (1024 * 1024)
    line_count = 0
    try:
        with open(file_path, "rb") as f:
            line_count = sum(1 for _ in f) - 1  # subtract header
    except Exception:
        line_count = -1

    return True, max(0, line_count), size_mb


def run_scraper(script_name: str) -> bool:
    """Executes a seed script using python interpreter."""
    script_path = BACKEND_DIR / "scripts" / "bddk" / script_name
    logger.info(f"Executing scraper: {script_path}...")
    result = subprocess.run(
        [sys.executable, str(script_path)],
        cwd=str(BACKEND_DIR.parent),
    )
    if result.returncode != 0:
        logger.error(f"Scraper {script_name} failed with exit code {result.returncode}!")
        return False
    return True


def main() -> None:
    args = parse_args()

    root_dir = BACKEND_DIR.parent
    bronze_bddk_dir = root_dir / "data" / "bronze" / "bddk"

    targets = [
        {
            "name": "Weekly Bulletin",
            "file": bronze_bddk_dir / "weekly" / "bddk_weekly_all_2021_2026.csv",
            "script": "seed_weekly.py",
            "flag": args.only_weekly,
        },
        {
            "name": "Monthly Bulletin",
            "file": bronze_bddk_dir / "monthly" / "bddk_monthly_all_2021_2026_precise.csv",
            "script": "seed_monthly.py",
            "flag": args.only_monthly,
        },
        {
            "name": "FinTürk Bulletin",
            "file": bronze_bddk_dir / "finturk" / "bddk_finturk_all_2021_2026.csv",
            "script": "seed_finturk.py",
            "flag": args.only_finturk,
        },
    ]

    has_specific_flag = (
        args.only_weekly or args.only_monthly or args.only_finturk
    )

    logger.info("=" * 70)
    logger.info("BDDK BRONZE LAYER BUILD STARTED")
    logger.info("=" * 70)
    logger.info(f"Bronze Directory : {bronze_bddk_dir}")
    logger.info(f"Full Refresh     : {args.full_refresh}")

    for target in targets:
        # If user specified a specific flag, skip non-matching targets
        if has_specific_flag and not target["flag"]:
            continue

        target_file = target["file"]
        name = target["name"]
        script = target["script"]

        exists, rows, size_mb = get_csv_stats(target_file)

        if exists and not args.full_refresh:
            logger.info(
                f"[SKIP] {name} already exists: {target_file.name} "
                f"({size_mb:.2f} MB, ~{rows:,} rows). Use --full-refresh to re-scrape."
            )
        else:
            logger.info(f"--- Fetching {name} ---")
            target_file.parent.mkdir(parents=True, exist_ok=True)
            success = run_scraper(script)
            if not success:
                logger.error(f"Failed to fetch {name}!")

    # Final verification & summary
    logger.info("")
    logger.info("=" * 70)
    logger.info("BDDK BRONZE BUILD SUMMARY")
    logger.info("=" * 70)

    for target in targets:
        target_file = target["file"]
        name = target["name"]
        exists, rows, size_mb = get_csv_stats(target_file)
        status = "READY" if exists else "MISSING"
        logger.info(
            f"[{status}] {name:18}: {target_file.name} "
            f"({size_mb:.2f} MB, {rows:,} rows)"
        )

    logger.info("=" * 70)


if __name__ == "__main__":
    main()
