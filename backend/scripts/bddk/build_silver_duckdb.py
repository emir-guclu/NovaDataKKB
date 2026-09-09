"""Materialize canonical BDDK Silver tables in DuckDB."""

from __future__ import annotations

from pathlib import Path

import duckdb


ROOT = Path(__file__).resolve().parents[3]

SILVER_DIR = ROOT / "data" / "silver" / "bddk"

OBSERVATIONS_PARQUET = (
    SILVER_DIR / "bddk_silver_observations.parquet"
)

CATALOG_PARQUET = (
    SILVER_DIR / "bddk_series_catalog.parquet"
)

DUCKDB_PATH = (
    SILVER_DIR / "bddk_silver.duckdb"
)


def main() -> None:
    if not OBSERVATIONS_PARQUET.exists():
        raise FileNotFoundError(
            f"Missing observations parquet: {OBSERVATIONS_PARQUET}"
        )

    if not CATALOG_PARQUET.exists():
        raise FileNotFoundError(
            f"Missing catalog parquet: {CATALOG_PARQUET}"
        )

    con = duckdb.connect(str(DUCKDB_PATH))

    try:
        con.execute(
            f"""
            CREATE OR REPLACE TABLE observations AS
            SELECT
                CAST(series_id AS VARCHAR) AS series_id,
                CAST(source AS VARCHAR) AS source,
                CAST(date AS DATE) AS date,
                CAST(period_start AS DATE) AS period_start,
                CAST(period_end AS DATE) AS period_end,
                CAST(value AS DOUBLE) AS value,
                CAST(freq AS VARCHAR) AS freq,
                CAST(unit AS VARCHAR) AS unit,
                CAST(dims AS JSON) AS dims,
                CAST(source_file AS VARCHAR) AS source_file
            FROM read_parquet(
                '{OBSERVATIONS_PARQUET.as_posix()}'
            )
            """
        )

        con.execute(
            f"""
            CREATE OR REPLACE TABLE series_catalog AS
            SELECT
                CAST(series_id AS VARCHAR) AS series_id,
                CAST(source AS VARCHAR) AS source,
                CAST(freq AS VARCHAR) AS freq,
                CAST(unit AS VARCHAR) AS unit,
                CAST(accumulation AS VARCHAR) AS accumulation,
                CAST(description AS VARCHAR) AS description,
                CAST(is_cumulative AS BOOLEAN) AS is_cumulative
            FROM read_parquet(
                '{CATALOG_PARQUET.as_posix()}'
            )
            """
        )

        observation_schema = con.execute(
            "DESCRIBE observations"
        ).fetchdf()

        catalog_schema = con.execute(
            "DESCRIBE series_catalog"
        ).fetchdf()

        stats = con.execute(
            """
            SELECT
                COUNT(*) AS observations,
                COUNT(DISTINCT series_id) AS series,
                COUNT(*) FILTER (
                    WHERE value IS NULL
                ) AS missing_values,
                COUNT(*) FILTER (
                    WHERE dims IS NULL
                ) AS null_dims,
                COUNT(*) FILTER (
                    WHERE date <> period_end
                ) AS invalid_date_boundaries
            FROM observations
            """
        ).fetchdf()

        duplicates = con.execute(
            """
            SELECT COUNT(*) AS duplicate_groups
            FROM (
                SELECT
                    series_id,
                    date,
                    dims,
                    COUNT(*) AS n
                FROM observations
                GROUP BY
                    series_id,
                    date,
                    dims
                HAVING COUNT(*) > 1
            )
            """
        ).fetchone()[0]

        catalog_stats = con.execute(
            """
            SELECT
                COUNT(*) AS catalog_rows,
                COUNT(DISTINCT series_id) AS unique_series,
                COUNT(*) FILTER (
                    WHERE accumulation = 'ytd'
                ) AS ytd_series,
                COUNT(*) FILTER (
                    WHERE is_cumulative
                ) AS cumulative_series
            FROM series_catalog
            """
        ).fetchdf()

        missing_catalog = con.execute(
            """
            SELECT COUNT(*)
            FROM (
                SELECT DISTINCT series_id
                FROM observations

                EXCEPT

                SELECT series_id
                FROM series_catalog
            )
            """
        ).fetchone()[0]

        orphan_catalog = con.execute(
            """
            SELECT COUNT(*)
            FROM (
                SELECT series_id
                FROM series_catalog

                EXCEPT

                SELECT DISTINCT series_id
                FROM observations
            )
            """
        ).fetchone()[0]

        dims_type = con.execute(
            """
            SELECT typeof(dims)
            FROM observations
            LIMIT 1
            """
        ).fetchone()[0]

        print("=" * 100)
        print("CANONICAL BDDK SILVER DUCKDB")
        print("=" * 100)

        print("\nOBSERVATIONS SCHEMA:")
        print(
            observation_schema.to_string(index=False)
        )

        print("\nCATALOG SCHEMA:")
        print(
            catalog_schema.to_string(index=False)
        )

        print("\nOBSERVATION STATS:")
        print(
            stats.to_string(index=False)
        )

        print("\nCATALOG STATS:")
        print(
            catalog_stats.to_string(index=False)
        )

        print("\nDIMS TYPE:", dims_type)
        print("DUPLICATE GROUPS:", duplicates)
        print("MISSING CATALOG SERIES:", missing_catalog)
        print("ORPHAN CATALOG SERIES:", orphan_catalog)

        if dims_type != "JSON":
            raise RuntimeError(
                f"dims is not native JSON: {dims_type}"
            )

        if duplicates != 0:
            raise RuntimeError(
                f"Found {duplicates} duplicate observation groups"
            )

        if missing_catalog != 0:
            raise RuntimeError(
                "Some observation series are missing from catalog"
            )

        if orphan_catalog != 0:
            raise RuntimeError(
                "Catalog contains series without observations"
            )

        print(
            "\nDuckDB artifact:",
            DUCKDB_PATH,
        )

    finally:
        con.close()


if __name__ == "__main__":
    main()
