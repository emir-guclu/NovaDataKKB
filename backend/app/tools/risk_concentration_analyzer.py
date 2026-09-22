from __future__ import annotations

import logging
import math
import re
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

_ENTITY_ALIASES = (
    "entity",
    "name",
    "label",
    "province",
    "sector",
    "sektor",
    "sektör",
    "firma",
    "kurum",
    "il",
    "banka",
    "kategori",
    "sirket",
    "şirket",
)
_VALUE_ALIASES = (
    "value",
    "amount",
    "tutar",
    "risk",
    "deger",
    "değer",
    "pay",
    "volume",
    "bakiye",
)


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


def _fold_key(k: Any) -> str:
    s = str(k).strip().lower()
    return (
        s.replace("ı", "i")
        .replace("i̇", "i")
        .replace("ğ", "g")
        .replace("ü", "u")
        .replace("ş", "s")
        .replace("ö", "o")
    )


def _find_alias_value(row: dict[str, Any], aliases: tuple[str, ...]) -> tuple[str | None, Any]:
    key_map: dict[str, tuple[str, Any]] = {}
    for k, v in row.items():
        key_map[_fold_key(k)] = (str(k), v)
    for alias in aliases:
        folded = _fold_key(alias)
        if folded in key_map:
            return key_map[folded]
    return None, None


def _clean_numeric_str(raw: str) -> str:
    # Remove currency symbols/suffixes like TL, TRY, $, €, NBSP, percent, whitespace
    return re.sub(r"[A-Za-z₺$€\s\u00a0%]", "", raw)


def _detect_dot_role(raw_values: list[str]) -> str:
    candidates = []
    for raw in raw_values:
        text = _clean_numeric_str(raw)
        if text.count(".") == 1 and "," not in text:
            candidates.append(text.split(".")[1])
    if not candidates:
        return "decimal"
    three_digit = sum(1 for tail in candidates if len(tail) == 3 and tail.isdigit())
    return "thousands" if (three_digit / len(candidates)) >= 0.7 else "decimal"


def _parse_item_value(raw: Any, dot_role: str = "decimal") -> float | None:
    if isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        val = float(raw)
        return val if math.isfinite(val) else None
    if isinstance(raw, str):
        text = _clean_numeric_str(raw)
        if not text:
            return None
        if "," in text:
            # Türkçe sayı formatı: "1.234,56" -> 1234.56
            text = text.replace(".", "").replace(",", ".")
        elif text.count(".") > 1:
            # Çoklu nokta binlik ayracı: "1.234.567" -> 1234567
            text = text.replace(".", "")
        elif dot_role == "thousands" and text.count(".") == 1:
            tail = text.split(".")[1]
            if len(tail) == 3 and tail.isdigit():
                text = text.replace(".", "")
        try:
            val = float(text)
            return val if math.isfinite(val) else None
        except ValueError:
            return None
    return None


def _parse_inline_items(
    items: list[dict[str, Any]],
) -> tuple[dict[str, float], list[str], str, str]:
    if not items or not isinstance(items, list):
        raise ValueError("Yoğunlaşma analizi için en az 2 geçerli varlık gereklidir; liste boş.")

    raw_val_strings = []
    for row in items:
        if isinstance(row, dict):
            _, val = _find_alias_value(row, _VALUE_ALIASES)
            if isinstance(val, str):
                raw_val_strings.append(val)

    dot_role = _detect_dot_role(raw_val_strings)
    warnings: list[str] = []
    entity_totals: dict[str, float] = {}
    detected_dim: str | None = None
    detected_met: str | None = None

    for item in items:
        if not isinstance(item, dict):
            warnings.append(f"Geçersiz satır formatı (sözlük bekleniyordu): {item}")
            continue

        dim_key, raw_entity = _find_alias_value(item, _ENTITY_ALIASES)
        val_key, raw_val = _find_alias_value(item, _VALUE_ALIASES)

        if dim_key and not detected_dim:
            detected_dim = dim_key
        if val_key and not detected_met:
            detected_met = val_key

        if not raw_entity or not str(raw_entity).strip():
            warnings.append(f"Varlık adı eksik veya boş olan satır atlandı: {item}")
            continue

        parsed_val = _parse_item_value(raw_val, dot_role)
        if parsed_val is None or parsed_val <= 0:
            warnings.append(f"'{raw_entity}' için pozitif sayısal değer okunamadı ({raw_val}), satır atlandı.")
            continue

        entity_name = str(raw_entity).strip()
        entity_totals[entity_name] = entity_totals.get(entity_name, 0.0) + parsed_val

    if len(entity_totals) < 2:
        raise ValueError("Yoğunlaşma analizi için en az 2 geçerli varlık gereklidir.")

    total_sum = sum(entity_totals.values())
    if total_sum <= 0:
        raise ValueError("Toplam metrik degeri sifir veya negatif.")

    return entity_totals, warnings, detected_dim or "entity", detected_met or "value"


class RiskConcentrationAnalyzerTool(BaseTool):
    name = "risk_concentration_analyzer"
    description = (
        "Kredi portföyü, takipteki alacaklar (NPL), dış kaynaklı portföy dökümleri veya sektörel "
        "risklerin bölgesel/kurumsal yoğunlaşmasını (CR3, CR5 ve Herfindahl-Hirschman Endeksi - HHI) "
        "hesaplar. Hem Lakehouse tablolarını hem de satır içi varlık listelerini (items) destekler. "
        "Pareto dağılımı ve kümülatif yoğunlaşma grafiği üretir. Zaman serisi değişimlerini veya "
        "makroekonomik döngüleri analiz etmek için KULLANMA; onlar için change_detection veya "
        "turning_point_and_cycle_detector kullanılmalıdır."
    )

    class Input(BaseModel):
        items: list[dict[str, Any]] | None = Field(
            default=None,
            description=(
                "Satır içi varlık listesi: [{'entity': 'Firma A', 'value': 120.5}, ...]. "
                "Lakehouse dışı kaynaklardan (yüklenen Excel/PDF/görsel, harici portföy) gelen "
                "risk veya pazar payı dağılımlarını analiz etmek için kullanılır. "
                "En az 2 varlık gerekir. items verilmişse table_name sorgulanmaz."
            ),
        )
        table_name: str | None = Field(
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
        data_source: str = "lakehouse"
        warnings: list[str] = Field(default_factory=list)
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
            if params.items is not None:
                # Satır içi (inline) mod
                try:
                    entity_totals, warnings, detected_dim, detected_met = _parse_inline_items(params.items)
                except ValueError as ve:
                    return self.Output(success=False, error=str(ve), data_source="inline")

                rows = sorted(entity_totals.items(), key=lambda x: x[1], reverse=True)
                resolved_table = None
                dimension_col = detected_dim
                metric_col = detected_met
                metric_unit = None
                selected_date = params.date
                data_source = "inline"
            else:
                # Lakehouse tablosu modu
                if not LAKEHOUSE_DB.exists():
                    return self.Output(success=False, error=f"Lakehouse bulunamadi: {LAKEHOUSE_DB}")

                con = _connect_lakehouse()
                try:
                    tables = {row[0] for row in con.execute("SHOW TABLES").fetchall()}

                    # Tablo adı eşleme
                    resolved_table = params.table_name
                    if resolved_table not in tables:
                        for t in tables:
                            if params.table_name and (params.table_name in t or t in params.table_name):
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

                dimension_col = params.dimension_column
                metric_col = params.metric_column
                metric_unit = _metric_unit(resolved_table, params.metric_column)
                warnings = []
                data_source = "lakehouse"

            if not rows:
                return self.Output(
                    success=False,
                    error="Sorgulanan kriterlere uygun veri bulunamadi.",
                    data_source=data_source,
                )

            total_metric_sum = sum(r[1] for r in rows)
            if total_metric_sum <= 0:
                return self.Output(
                    success=False,
                    error="Toplam metrik degeri sifir veya negatif.",
                    data_source=data_source,
                )

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

            top_entities = []
            for idx, s in enumerate(shares[:params.top_k]):
                entry: dict[str, Any] = {
                    "rank": idx + 1,
                    dimension_col: s[0],
                    "amount": round(s[1], 2),
                    "share_pct": round(s[2], 2),
                }
                if "entity" not in entry:
                    entry["entity"] = s[0]
                top_entities.append(entry)

            chart_labels = [s[0] for s in shares[:10]]
            chart_values = [s[1] for s in shares[:10]]

            chart_url = generate_concentration_chart(
                labels=chart_labels,
                values=chart_values,
                cr3_pct=round(cr3_pct, 1),
                cr5_pct=round(cr5_pct, 1),
                hhi_score=round(hhi, 1),
                dimension_name=dimension_col,
            )

            return self.Output(
                success=True,
                data_source=data_source,
                warnings=warnings,
                table_name=resolved_table,
                dimension_column=dimension_col,
                metric_column=metric_col,
                metric_unit=metric_unit,
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
            return self.Output(
                success=False,
                error=str(exc),
                data_source="inline" if params.items is not None else "lakehouse",
            )
