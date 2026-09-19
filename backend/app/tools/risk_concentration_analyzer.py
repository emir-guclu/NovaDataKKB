from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import duckdb
from pydantic import BaseModel, Field

from backend.app.services.chart_generator import generate_concentration_chart
from backend.app.tools.base import BaseTool
from backend.app.models.lakehouse_models import lakehouse_metadata

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
LAKEHOUSE_DB = PROJECT_ROOT / "data" / "lakehouse.duckdb"
SILVER_DB = PROJECT_ROOT / "data" / "silver" / "silver.duckdb"
ALIGNED_DB = PROJECT_ROOT / "data" / "aligned" / "monthly" / "aligned.duckdb"
GOLD_DIR = PROJECT_ROOT / "data" / "gold"


def _quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _sql_string_literal(value: str) -> str:
    return value.replace("'", "''")


def _connect_lakehouse() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(str(LAKEHOUSE_DB), read_only=True)
    if SILVER_DB.exists():
        con.execute(f"ATTACH IF NOT EXISTS '{_sql_string_literal(SILVER_DB.resolve().as_posix())}' AS silver_db (READ_ONLY)")
    if ALIGNED_DB.exists():
        con.execute(f"ATTACH IF NOT EXISTS '{_sql_string_literal(ALIGNED_DB.resolve().as_posix())}' AS aligned_db (READ_ONLY)")

    if GOLD_DIR.exists():
        for parquet_path in sorted(GOLD_DIR.glob("*.parquet")):
            view_name = parquet_path.stem
            parquet_sql_path = _sql_string_literal(parquet_path.resolve().as_posix())
            con.execute(
                f"CREATE OR REPLACE TEMP VIEW {_quote_identifier(view_name)} "
                f"AS SELECT * FROM read_parquet('{parquet_sql_path}')"
            )
    return con


def _metric_unit(table_name: str, metric_column: str) -> str | None:
    table = lakehouse_metadata.tables.get(table_name)
    if table is None or metric_column not in table.c:
        return None
    unit = table.c[metric_column].info.get("unit")
    return str(unit) if unit else None


class RiskConcentrationAnalyzerTool(BaseTool):
    name = "risk_concentration_analyzer"
    description = (
        "Kredi portföyü, takipteki alacaklar (NPL) veya sektörel risklerin bölgesel/kurumsal "
        "yoğunlaşmasını (CR3, CR5 ve Herfindahl-Hirschman Endeksi - HHI) hesaplar. "
        "Pareto dağılımı ve kümülatif yoğunlaşma grafiği üretir. Zaman serisi değişimlerini veya "
        "makroekonomik döngüleri analiz etmek için KULLANMA; onlar için change_detection veya "
        "turning_point_and_cycle_detector kullanılmalıdır. Örnek table_name: 'gold_finturk_province_credit_quality', "
        "dimension_column: 'province', metric_column: 'nonperforming_receivables'."
    )

    class Input(BaseModel):
        table_name: str = Field(
            default="gold_finturk_province_credit_quality",
            description="Lakehouse tablosu (örn. 'gold_finturk_province_credit_quality' veya 'gold_finturk')",
        )
        dimension_column: str = Field(
            default="province",
            description="Analiz edilecek boyut kolonu (örn. province, sector)",
        )
        metric_column: str = Field(
            default="nonperforming_receivables",
            description="Risk metriği kolonu (örn. nonperforming_receivables, total_cash_loans)",
        )
        date: str | None = Field(
            default=None,
            description="Analiz tarihi (YYYY-MM-DD). Belirtilmezse en son mevcut tarih kullanılır.",
        )
        top_k: int = Field(default=5, ge=1, le=50, description="Listelenecek lider varlık sayısı")

    class Output(BaseModel):
        success: bool
        error: str | None = None
        table_name: str | None = None
        dimension_column: str | None = None
        metric_column: str | None = None
        metric_unit: str | None = None
        date_analyzed: str | None = None
        total_risk_amount: float | None = None
        cr3_share_pct: float | None = None
        cr5_share_pct: float | None = None
        hhi_score: float | None = None
        hhi_level: str | None = None
        top_entities: list[dict[str, Any]] = Field(default_factory=list)
        chart_url: str | None = None

    def run(self, params: Input) -> Output:
        try:
            if not LAKEHOUSE_DB.exists():
                return self.Output(success=False, error=f"Lakehouse bulunamadi: {LAKEHOUSE_DB}")

            con = _connect_lakehouse()
            try:
                tables = {row[0] for row in con.execute("SHOW TABLES").fetchall()}

                # Tablo adı eşleme
                resolved_table = params.table_name
                if resolved_table not in tables:
                    for t in tables:
                        if params.table_name in t or t in params.table_name:
                            resolved_table = t
                            break

                if resolved_table not in tables:
                    return self.Output(success=False, error=f"Tablo bulunamadi: {params.table_name}")

                schema_rows = con.execute(f"DESCRIBE {_quote_identifier(resolved_table)}").fetchall()
                available_columns = {row[0] for row in schema_rows}

                if params.dimension_column not in available_columns:
                    return self.Output(
                        success=False,
                        error=f"Boyut kolonu bulunamadi: {params.dimension_column}. Mevcut: {sorted(available_columns)}",
                    )
                if params.metric_column not in available_columns:
                    return self.Output(
                        success=False,
                        error=f"Metrik kolonu bulunamadi: {params.metric_column}. Mevcut: {sorted(available_columns)}",
                    )

                # Tarih belirleme
                has_date_col = "date" in available_columns
                selected_date = params.date
                if has_date_col and not selected_date:
                    max_date_row = con.execute(f"SELECT MAX(date) FROM {_quote_identifier(resolved_table)}").fetchone()
                    if max_date_row and max_date_row[0]:
                        selected_date = str(max_date_row[0])[:10]

                where_clauses = []
                query_params: list[Any] = []

                if has_date_col and selected_date:
                    where_clauses.append("CAST(date AS VARCHAR) LIKE ?")
                    query_params.append(f"{selected_date}%")

                if "geo_level" in available_columns and params.dimension_column == "province":
                    where_clauses.append("geo_level = 'province'")

                where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

                sql = f"""
                    SELECT {_quote_identifier(params.dimension_column)} as entity,
                           SUM(CAST({_quote_identifier(params.metric_column)} AS DOUBLE)) as total_metric
                    FROM {_quote_identifier(resolved_table)}
                    {where_sql}
                    GROUP BY {_quote_identifier(params.dimension_column)}
                    HAVING total_metric > 0
                    ORDER BY total_metric DESC
                """

                rows = con.execute(sql, query_params).fetchall()
            finally:
                con.close()

            if not rows:
                return self.Output(success=False, error="Sorgulanan kriterlere uygun veri bulunamadi.")

            total_metric_sum = sum(r[1] for r in rows)
            if total_metric_sum <= 0:
                return self.Output(success=False, error="Toplam metrik degeri sifir veya negatif.")

            shares = [(r[0], float(r[1]), (float(r[1]) / total_metric_sum) * 100.0) for r in rows]

            # CR3, CR5 hesapla
            cr3_pct = sum(s[2] for s in shares[:3]) if len(shares) >= 3 else sum(s[2] for s in shares)
            cr5_pct = sum(s[2] for s in shares[:5]) if len(shares) >= 5 else sum(s[2] for s in shares)

            # HHI = sum((market_share_pct)^2)
            hhi = sum(s[2] ** 2 for s in shares)

            if hhi > 2500:
                hhi_level = "Yüksek Yoğunlaşma / Kritik Risk Kümelenmesi"
            elif hhi >= 1500:
                hhi_level = "Orta Düzey Yoğunlaşma"
            else:
                hhi_level = "Düşük Yoğunlaşma / Dengeli Dağılım"

            top_entities = [
                {
                    "rank": idx + 1,
                    params.dimension_column: s[0],
                    "amount": round(s[1], 2),
                    "share_pct": round(s[2], 2),
                }
                for idx, s in enumerate(shares[:params.top_k])
            ]

            chart_labels = [s[0] for s in shares[:10]]
            chart_values = [s[1] for s in shares[:10]]

            chart_url = generate_concentration_chart(
                labels=chart_labels,
                values=chart_values,
                cr3_pct=round(cr3_pct, 1),
                cr5_pct=round(cr5_pct, 1),
                hhi_score=round(hhi, 1),
                dimension_name=params.dimension_column,
            )

            return self.Output(
                success=True,
                table_name=resolved_table,
                dimension_column=params.dimension_column,
                metric_column=params.metric_column,
                metric_unit=_metric_unit(resolved_table, params.metric_column),
                date_analyzed=selected_date,
                total_risk_amount=round(total_metric_sum, 2),
                cr3_share_pct=round(cr3_pct, 2),
                cr5_share_pct=round(cr5_pct, 2),
                hhi_score=round(hhi, 2),
                hhi_level=hhi_level,
                top_entities=top_entities,
                chart_url=chart_url,
            )

        except Exception as exc:
            logger.exception("risk_concentration_analyzer failed")
            return self.Output(success=False, error=str(exc))
