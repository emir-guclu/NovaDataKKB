from __future__ import annotations

import logging
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any, Literal

import duckdb
from pydantic import BaseModel, Field

from backend.app.tools.base import BaseTool

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
LAKEHOUSE_DB = PROJECT_ROOT / "data" / "lakehouse.duckdb"
SILVER_DB = PROJECT_ROOT / "data" / "silver" / "silver.duckdb"
ALIGNED_DB = PROJECT_ROOT / "data" / "aligned" / "monthly" / "aligned.duckdb"
GOLD_DIR = PROJECT_ROOT / "data" / "gold"
EVDS_CATALOG = PROJECT_ROOT / "data" / "bronze" / "evds" / "evds_catalog.parquet"

FORBIDDEN_KEYWORDS = [
    "DROP",
    "DELETE",
    "INSERT",
    "UPDATE",
    "ALTER",
    "CREATE",
    "ATTACH",
    "COPY",
]


_FORBIDDEN_RE = re.compile(
    r"\b(" + "|".join(FORBIDDEN_KEYWORDS) + r")\b", re.IGNORECASE
)


def validate_query_safety(sql: str) -> tuple[bool, str | None]:
    match = _FORBIDDEN_RE.search(sql)
    if match:
        kw = match.group(1).upper()
        return False, f"Bu sorgu türü ({kw}) desteklenmiyor, sadece SELECT kullanılabilir."
    return True, None


def _quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _json_ready(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


def _sql_string_literal(value: str) -> str:
    return value.replace("'", "''")


def _bind_local_parquet_views(con: duckdb.DuckDBPyConnection) -> None:
    """Makineye ozel persistent view pathlerini local repo Parquetleriyle golgeler."""
    if GOLD_DIR.exists():
        for parquet_path in sorted(GOLD_DIR.glob("*.parquet")):
            view_name = parquet_path.stem
            parquet_sql_path = _sql_string_literal(parquet_path.resolve().as_posix())
            con.execute(
                f"CREATE OR REPLACE TEMP VIEW {_quote_identifier(view_name)} "
                f"AS SELECT * FROM read_parquet('{parquet_sql_path}')"
            )

    if EVDS_CATALOG.exists():
        evds_sql_path = _sql_string_literal(EVDS_CATALOG.resolve().as_posix())
        con.execute(
            f"CREATE OR REPLACE TEMP VIEW {_quote_identifier('gold_evds_catalog')} "
            f"AS SELECT * FROM read_parquet('{evds_sql_path}')"
        )


def _connect_lakehouse() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(str(LAKEHOUSE_DB), read_only=True)
    if SILVER_DB.exists():
        con.execute(f"ATTACH IF NOT EXISTS '{_sql_string_literal(SILVER_DB.resolve().as_posix())}' AS silver_db (READ_ONLY)")
    if ALIGNED_DB.exists():
        con.execute(f"ATTACH IF NOT EXISTS '{_sql_string_literal(ALIGNED_DB.resolve().as_posix())}' AS aligned_db (READ_ONLY)")

    _bind_local_parquet_views(con)
    return con


class LakehouseQueryTool(BaseTool):
    name = "lakehouse_query"
    description = (
        "Lakehouse icindeki hazir Silver, Aligned ve Gold tablolarindan guvenli, "
        "sinirli veri getirir. Guncel/harici internet bilgisi icin KULLANMA; onun "
        "icin web_search kullanilmalidir. Ham SQL almaz; table, columns, filters "
        "ve limit gibi yapilandirilmis parametrelerle cagrilir. Ornek table: "
        "'gold_housing_credit_market', columns: ['date', 'konut_kredisi_faiz_orani']."
    )

    class Input(BaseModel):
        table: str = Field(description="Lakehouse tablosu veya view adi")
        columns: list[str] = Field(description="Getirilecek kolon adlari")
        filters: dict[str, Any] = Field(
            default_factory=dict,
            description="Kolon-esitlik filtreleri. Ornek: {'geo_level': 'province'}",
        )
        start_date: str | None = Field(default=None, description="Opsiyonel baslangic tarihi, YYYY-MM-DD")
        end_date: str | None = Field(default=None, description="Opsiyonel bitis tarihi, YYYY-MM-DD")
        date_column: str = Field(default="date", description="Tarih filtresi icin kullanilacak kolon")
        order_by: str | None = Field(default=None, description="Opsiyonel siralama kolonu")
        order_direction: Literal["asc", "desc"] = Field(default="asc", description="Siralama yonu")
        limit: int = Field(default=50, ge=1, le=500, description="Maksimum satir sayisi")

    class Output(BaseModel):
        success: bool
        error: str | None = None
        table: str | None = None
        row_count: int = 0
        rows: list[dict[str, Any]] = Field(default_factory=list)

    def run(self, params: Input) -> Output:
        try:
            if not LAKEHOUSE_DB.exists():
                return self.Output(success=False, error=f"Lakehouse bulunamadi: {LAKEHOUSE_DB}")

            if not params.columns:
                return self.Output(success=False, error="En az bir kolon belirtilmelidir.")

            if bool(params.start_date) != bool(params.end_date):
                return self.Output(success=False, error="start_date ve end_date birlikte verilmelidir.")

            con = _connect_lakehouse()
            try:
                tables = {row[0] for row in con.execute("SHOW TABLES").fetchall()}
                if params.table not in tables:
                    return self.Output(success=False, error=f"Tablo bulunamadi: {params.table}")

                schema_rows = con.execute(f"DESCRIBE {_quote_identifier(params.table)}").fetchall()
                available_columns = {row[0] for row in schema_rows}
                requested_columns = set(params.columns)
                extra_columns = requested_columns - available_columns
                if extra_columns:
                    return self.Output(
                        success=False,
                        error=f"Kolon bulunamadi: {sorted(extra_columns)}",
                        table=params.table,
                    )

                referenced_columns = set(params.filters.keys())
                if params.start_date and params.end_date:
                    referenced_columns.add(params.date_column)
                if params.order_by:
                    referenced_columns.add(params.order_by)

                extra_referenced = referenced_columns - available_columns
                if extra_referenced:
                    return self.Output(
                        success=False,
                        error=f"Kolon bulunamadi: {sorted(extra_referenced)}",
                        table=params.table,
                    )

                where_clauses: list[str] = []
                query_params: list[Any] = []
                for column, value in params.filters.items():
                    where_clauses.append(f"{_quote_identifier(column)} = ?")
                    query_params.append(value)

                if params.start_date and params.end_date:
                    where_clauses.append(f"{_quote_identifier(params.date_column)} BETWEEN ? AND ?")
                    query_params.extend([params.start_date, params.end_date])

                sql = (
                    f"SELECT {', '.join(_quote_identifier(column) for column in params.columns)} "
                    f"FROM {_quote_identifier(params.table)}"
                )
                if where_clauses:
                    sql += " WHERE " + " AND ".join(where_clauses)
                if params.order_by:
                    sql += f" ORDER BY {_quote_identifier(params.order_by)} {params.order_direction.upper()}"
                sql += " LIMIT ?"
                query_params.append(params.limit)

                is_safe, safety_err = validate_query_safety(sql)
                if not is_safe:
                    return self.Output(success=False, error=safety_err, table=params.table)

                cursor = con.execute(sql, query_params)
                columns = [col[0] for col in cursor.description]
                rows = [
                    {column: _json_ready(value) for column, value in zip(columns, row)}
                    for row in cursor.fetchall()
                ]
            finally:
                con.close()

            return self.Output(
                success=True,
                table=params.table,
                row_count=len(rows),
                rows=rows,
            )
        except Exception as exc:
            logger.exception("lakehouse_query failed")
            return self.Output(success=False, error=str(exc), table=params.table)
