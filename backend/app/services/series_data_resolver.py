from __future__ import annotations

import logging
import unicodedata
from pathlib import Path
from typing import Any

import duckdb

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SILVER_DB = PROJECT_ROOT / "data" / "silver" / "silver.duckdb"
GOLD_PARQUET = PROJECT_ROOT / "data" / "gold" / "gold_periodic_change.parquet"
ALIGNED_PARQUET = PROJECT_ROOT / "data" / "aligned" / "monthly" / "observations.parquet"


def canonical_identifier(value: str) -> str:
    """Türkçe karakterleri normalize eder ve harf büyüklüğünü eşitleştirir."""
    translation = str.maketrans({
        "ı": "i", "İ": "I", "ş": "s", "Ş": "S",
        "ğ": "g", "Ğ": "G", "ü": "u", "Ü": "U",
        "ö": "o", "Ö": "O", "ç": "c", "Ç": "C",
    })
    normalized = value.translate(translation)
    return unicodedata.normalize("NFKC", normalized).casefold()


def attach_silver_db(con: duckdb.DuckDBPyConnection, db_path: Path = SILVER_DB) -> bool:
    """Silver duckdb veritabanını mevcut duckdb bağlantısına ekler (ATTACH)."""
    if not db_path.exists():
        return False
    try:
        databases = [row[1] for row in con.execute("PRAGMA database_list").fetchall()]
        if "silver_db" not in databases:
            con.execute(f"ATTACH '{db_path.as_posix()}' AS silver_db (READ_ONLY)")
        return True
    except Exception as exc:
        logger.warning("silver_db attach edilemedi: %s", exc)
        return False


def resolve_series_location(
    con: duckdb.DuckDBPyConnection,
    requested_id: str,
    parquet_path: Path,
    silver_db_path: Path = SILVER_DB,
) -> tuple[str | None, str | None]:
    """Seriyi önce parquet dosyasında arar, bulunamazsa silver.duckdb içinde arar.

    Döndürür: (matched_series_id, source_type) -> source_type: 'parquet' | 'silver' | None
    """
    canonical_req = canonical_identifier(requested_id)

    # 1. Aşama: Parquet kontrolü
    if parquet_path.exists():
        try:
            parquet_rows = con.execute(
                "SELECT DISTINCT series_id FROM read_parquet(?)",
                [str(parquet_path)],
            ).fetchall()
            all_parquet_ids = [r[0] for r in parquet_rows]
            for sid in all_parquet_ids:
                if canonical_identifier(sid) == canonical_req:
                    return sid, "parquet"
            for sid in all_parquet_ids:
                if sid.endswith(requested_id) or requested_id.endswith(sid):
                    return sid, "parquet"
        except Exception as exc:
            logger.debug("Parquet read failed for %s: %s", parquet_path, exc)

    # 2. Aşama: Silver duckdb fallback
    if attach_silver_db(con, silver_db_path):
        try:
            silver_rows = con.execute(
                "SELECT DISTINCT series_id FROM silver_db.observations"
            ).fetchall()
            all_silver_ids = [r[0] for r in silver_rows]
            for sid in all_silver_ids:
                if canonical_identifier(sid) == canonical_req:
                    return sid, "silver"
            for sid in all_silver_ids:
                if sid.endswith(requested_id) or requested_id.endswith(sid):
                    return sid, "silver"
        except Exception as exc:
            logger.warning("Silver duckdb query failed: %s", exc)

    return None, None


def get_available_dimensions(
    con: duckdb.DuckDBPyConnection,
    series_id: str,
    source: str,
    parquet_path: Path,
) -> list[str]:
    """Seriye ait mevcut dimension ('$.variable') listesini döner."""
    try:
        if source == "parquet":
            rows = con.execute(
                """
                SELECT DISTINCT json_extract_string(dims, '$.variable') AS dimension
                FROM read_parquet(?)
                WHERE series_id = ?
                ORDER BY dimension
                """,
                [str(parquet_path), series_id],
            ).fetchall()
        elif source == "silver":
            rows = con.execute(
                """
                SELECT DISTINCT json_extract_string(dims, '$.variable') AS dimension
                FROM silver_db.observations
                WHERE series_id = ?
                ORDER BY dimension
                """,
                [series_id],
            ).fetchall()
        else:
            return []
        return [r[0] for r in rows if r[0] is not None]
    except Exception as exc:
        logger.debug("Dimension query failed for %s (%s): %s", series_id, source, exc)
        return []


def resolve_dimension(
    available_dims: list[str],
    requested_dimension: str | None,
) -> tuple[str | None, str | None]:
    """Dimension çözümlemesi yapar.

    Döndürür: (seçilen_dimension, hata_mesajı)
    """
    if requested_dimension is not None:
        if requested_dimension in available_dims:
            return requested_dimension, None
        if not available_dims:
            return None, None
        return None, f"Dimension bulunamadi: {requested_dimension}. Mevcut dimensionlar: {available_dims}"

    if not available_dims:
        return None, None
    if len(available_dims) == 1:
        return available_dims[0], None
    if "Toplam" in available_dims:
        return "Toplam", None
    return None, f"Seri birden fazla dimension iceriyor. dimension belirtin: {available_dims}"


def _escape_sql_literal(val: str) -> str:
    return val.replace("'", "''")


def create_silver_periodic_view(
    con: duckdb.DuckDBPyConnection,
    view_name: str,
    series_id: str,
    dimension: str | None = None,
) -> None:
    """Silver.duckdb serisi üzerinde gold_periodic_change ile aynı şemada geçici bir DuckDB view oluşturur."""
    escaped_id = _escape_sql_literal(series_id)
    clauses = [f"series_id = '{escaped_id}'"]

    if dimension is not None:
        escaped_dim = _escape_sql_literal(dimension)
        clauses.append(f"json_extract_string(dims, '$.variable') = '{escaped_dim}'")

    sql = f"""
    CREATE OR REPLACE TEMPORARY VIEW {view_name} AS
    WITH base AS (
        SELECT 
            series_id,
            CAST(date AS DATE) AS date,
            value,
            LAG(CAST(date AS DATE), 1) OVER (ORDER BY date) AS prev_date_1,
            LAG(value, 1) OVER (ORDER BY date) AS prev_value_1,
            LAG(CAST(date AS DATE), 12) OVER (ORDER BY date) AS prev_date_12,
            LAG(value, 12) OVER (ORDER BY date) AS prev_value_12,
            source,
            unit,
            dims
        FROM silver_db.observations
        WHERE {' AND '.join(clauses)}
    )
    SELECT 
        date,
        series_id,
        value,
        CASE 
            WHEN ((year(date) - year(prev_date_1)) * 12 + (month(date) - month(prev_date_1))) = 1 
            THEN value - prev_value_1 
            ELSE NULL 
        END AS mom_abs_change,
        CASE 
            WHEN ((year(date) - year(prev_date_1)) * 12 + (month(date) - month(prev_date_1))) = 1 AND prev_value_1 IS NOT NULL AND prev_value_1 != 0 
            THEN (value - prev_value_1) / ABS(prev_value_1) 
            ELSE NULL 
        END AS mom_pct_change,
        CASE 
            WHEN ((year(date) - year(prev_date_12)) * 12 + (month(date) - month(prev_date_12))) = 12 
            THEN value - prev_value_12 
            ELSE NULL 
        END AS yoy_abs_change,
        CASE 
            WHEN ((year(date) - year(prev_date_12)) * 12 + (month(date) - month(prev_date_12))) = 12 AND prev_value_12 IS NOT NULL AND prev_value_12 != 0 
            THEN (value - prev_value_12) / ABS(prev_value_12) 
            ELSE NULL 
        END AS yoy_pct_change,
        source,
        'unclassified' AS nature,
        unit,
        dims
    FROM base
    ORDER BY date
    """
    con.execute(sql)


def fetch_series_observations(
    con: duckdb.DuckDBPyConnection,
    series_id: str,
    dimension: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    parquet_path: Path = ALIGNED_PARQUET,
    silver_db_path: Path = SILVER_DB,
) -> tuple[dict[str, float] | None, str | None, str | None, str | None]:
    """Seri gözlemlerini parquet veya silver.duckdb üzerinden okur.

    Döndürür: (tarih_değer_sözlüğü, çözülen_series_id, seçilen_dimension, hata_mesajı)
    """
    matched_id, source = resolve_series_location(con, series_id, parquet_path, silver_db_path)
    if not matched_id or not source:
        return None, None, None, f"Seri bulunamadi: {series_id}"

    available_dims = get_available_dimensions(con, matched_id, source, parquet_path)
    selected_dim, dim_err = resolve_dimension(available_dims, dimension)
    if dim_err:
        return None, matched_id, None, dim_err

    clauses = ["series_id = ?"]
    params: list[Any] = [matched_id]
    if selected_dim:
        clauses.append("json_extract_string(dims, '$.variable') = ?")
        params.append(selected_dim)

    if start_date:
        clauses.append("CAST(date AS DATE) >= CAST(? AS DATE)")
        params.append(start_date)
    if end_date:
        clauses.append("CAST(date AS DATE) <= CAST(? AS DATE)")
        params.append(end_date)

    where_sql = " AND ".join(clauses)

    if source == "parquet":
        sql = f"""
            SELECT strftime(CAST(date AS DATE), '%Y-%m-%d') as dt, value
            FROM read_parquet(?)
            WHERE {where_sql}
            ORDER BY date
        """
        rows = con.execute(sql, [str(parquet_path), *params]).fetchall()
    else:
        sql = f"""
            SELECT strftime(CAST(date AS DATE), '%Y-%m-%d') as dt, value
            FROM silver_db.observations
            WHERE {where_sql}
            ORDER BY date
        """
        rows = con.execute(sql, params).fetchall()

    data = {r[0]: float(r[1]) for r in rows if r[1] is not None}
    return data, matched_id, selected_dim, None
