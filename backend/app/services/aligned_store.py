"""Persistence helpers for the monthly aligned analytical layer."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd


def upsert_single_series_to_aligned_duckdb(
    *,
    db_path: Path,
    series_id: str,
    aligned: pd.DataFrame,
    metadata: pd.DataFrame,
) -> None:
    """Transactionally replace one series in aligned.duckdb."""
    if aligned.empty:
        raise ValueError(f"Aligned observations are empty for {series_id!r}")

    if set(aligned["series_id"].astype(str)) != {series_id}:
        raise ValueError("Aligned observations contain unexpected series_id values")

    if len(metadata) != 1 or str(metadata.iloc[0]["series_id"]) != series_id:
        raise ValueError("Aligned metadata must contain exactly the requested series")

    con = duckdb.connect(str(db_path))
    try:
        columns = {
            row[0]
            for row in con.execute("DESCRIBE series_metadata").fetchall()
        }
        if "nature_reviewed" not in columns:
            raise RuntimeError(
                "aligned.duckdb schema is stale: nature_reviewed is missing; "
                "rebuild the aligned layer before live aligned upserts"
            )

        con.execute("BEGIN TRANSACTION")

        con.execute(
            "DELETE FROM observations WHERE series_id = ?",
            [series_id],
        )
        con.execute(
            "DELETE FROM series_metadata WHERE series_id = ?",
            [series_id],
        )

        con.register("_aligned_new", aligned)
        con.execute(
            """
            INSERT INTO observations (
                series_id,
                source,
                date,
                value,
                source_freq,
                aligned_freq,
                unit,
                dims,
                alignment_method,
                is_imputed
            )
            SELECT
                CAST(series_id AS VARCHAR),
                CAST(source AS VARCHAR),
                CAST(date AS DATE),
                CAST(value AS DOUBLE),
                CAST(source_freq AS VARCHAR),
                CAST(aligned_freq AS VARCHAR),
                CAST(unit AS VARCHAR),
                CAST(dims AS JSON),
                CAST(alignment_method AS VARCHAR),
                CAST(is_imputed AS BOOLEAN)
            FROM _aligned_new
            """
        )

        con.register("_aligned_meta_new", metadata)
        con.execute(
            """
            INSERT INTO series_metadata (
                series_id,
                source,
                series_code,
                series_name,
                category,
                freq,
                unit,
                description,
                tags,
                accumulation,
                is_cumulative,
                nature,
                nature_reviewed,
                alignment_override
            )
            SELECT
                CAST(series_id AS VARCHAR),
                CAST(source AS VARCHAR),
                CAST(series_code AS VARCHAR),
                CAST(series_name AS VARCHAR),
                CAST(category AS VARCHAR),
                CAST(freq AS VARCHAR),
                CAST(unit AS VARCHAR),
                CAST(description AS VARCHAR),
                tags,
                CAST(accumulation AS VARCHAR),
                CAST(is_cumulative AS BOOLEAN),
                CAST(nature AS VARCHAR),
                CAST(nature_reviewed AS BOOLEAN),
                CAST(alignment_override AS VARCHAR)
            FROM _aligned_meta_new
            """
        )

        con.execute("COMMIT")
    except Exception:
        try:
            con.execute("ROLLBACK")
        except Exception:
            pass
        raise
    finally:
        con.close()
