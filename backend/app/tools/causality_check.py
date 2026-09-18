from __future__ import annotations

import logging
import math
import unicodedata
from pathlib import Path
from typing import Literal

import duckdb
from pydantic import BaseModel, Field

from backend.app.services.series_data_resolver import (
    GOLD_PARQUET,
    SILVER_DB,
    canonical_identifier,
    create_silver_periodic_view,
    get_available_dimensions,
    resolve_dimension,
    resolve_series_location,
)
from backend.app.tools.base import BaseTool

logger = logging.getLogger(__name__)

SUPPORTED_METRICS = {"value", "mom_abs_change", "mom_pct_change", "yoy_abs_change", "yoy_pct_change"}


def _canonical_identifier(value: str) -> str:
    return canonical_identifier(value)


def _resolve_series_and_dimension(
    con: duckdb.DuckDBPyConnection,
    requested_series_id: str,
    requested_dimension: str | None,
) -> tuple[str | None, str | None, str | None, str | None]:
    matched_id, source = resolve_series_location(con, requested_series_id, GOLD_PARQUET, SILVER_DB)
    if not matched_id or not source:
        return None, None, None, f"Seri bulunamadi: {requested_series_id}"

    available_dims = get_available_dimensions(con, matched_id, source, GOLD_PARQUET)
    dimension, dim_err = resolve_dimension(available_dims, requested_dimension)
    if dim_err:
        return matched_id, None, source, dim_err

    return matched_id, dimension, source, None


class CausalityCheckTool(BaseTool):
    name = "causality_check"
    description = (
        "Iki finansal seri arasindaki Pearson korelasyon katsayisini gercek "
        "gold_periodic_change verisi uzerinden hesaplar. Bu istatistiksel "
        "korelasyondur, kesin nedensellik ispati degildir; tek seri degisimleri "
        "icin KULLANMA, onun icin change_detection veya anomaly_detection kullan. "
        "Ornek: series_id_a='BDDK_MONTHLY:tuketici_kredileri:tuketici_kredileri_konut', "
        "dimension_a='Toplam', series_id_b='EVDS:TP.KTF12'."
    )

    class Input(BaseModel):
        series_id_a: str = Field(description="Birinci gold_periodic_change series_id")
        series_id_b: str = Field(description="Ikinci gold_periodic_change series_id")
        dimension_a: str | None = Field(default=None, description="Birinci seri dimension degeri")
        dimension_b: str | None = Field(default=None, description="Ikinci seri dimension degeri")
        metric: Literal["value", "mom_abs_change", "mom_pct_change", "yoy_abs_change", "yoy_pct_change"] = Field(
            default="value",
            description="Korelasyon icin kullanilacak metrik",
        )
        start_date: str | None = Field(default=None, description="Opsiyonel baslangic tarihi, YYYY-MM-DD")
        end_date: str | None = Field(default=None, description="Opsiyonel bitis tarihi, YYYY-MM-DD")

    class Output(BaseModel):
        success: bool
        error: str | None = None
        metric: str | None = None
        selected_dimension_a: str | None = None
        selected_dimension_b: str | None = None
        correlation_coefficient: float | None = None
        n_observations: int = 0
        interpretation: str = ""

    def run(self, params: Input) -> Output:
        try:
            if not GOLD_PARQUET.exists():
                return self.Output(success=False, error=f"Gold parquet bulunamadi: {GOLD_PARQUET}")

            if bool(params.start_date) != bool(params.end_date):
                return self.Output(success=False, error="start_date ve end_date birlikte verilmelidir.")

            con = duckdb.connect()
            try:
                series_a, dimension_a, source_a, error = _resolve_series_and_dimension(
                    con, params.series_id_a, params.dimension_a
                )
                if error:
                    return self.Output(success=False, error=error, metric=params.metric)

                series_b, dimension_b, source_b, error = _resolve_series_and_dimension(
                    con, params.series_id_b, params.dimension_b
                )
                if error:
                    return self.Output(success=False, error=error, metric=params.metric)

                def _build_source_cte(series_id: str, dimension: str | None, source: str, alias: str) -> tuple[str, list[Any]]:
                    where = []
                    qparams: list[Any] = []
                    if source == "silver":
                        view_name = f"view_{alias}"
                        create_silver_periodic_view(con, view_name, series_id, dimension)
                        cte_sql = f"SELECT CAST(date AS DATE) AS date, {params.metric} AS value_{alias} FROM {view_name}"
                        if params.start_date and params.end_date:
                            where.append("date BETWEEN ? AND ?")
                            qparams.extend([params.start_date, params.end_date])
                        if where:
                            cte_sql += f" WHERE {' AND '.join(where)}"
                        return cte_sql, qparams
                    else:
                        where.append("series_id = ?")
                        qparams.append(series_id)
                        if dimension is None:
                            where.append("json_extract_string(dims, '$.variable') IS NULL")
                        else:
                            where.append("json_extract_string(dims, '$.variable') = ?")
                            qparams.append(dimension)
                        if params.start_date and params.end_date:
                            where.append("CAST(date AS DATE) BETWEEN ? AND ?")
                            qparams.extend([params.start_date, params.end_date])
                        cte_sql = f"""
                            SELECT CAST(date AS DATE) AS date, {params.metric} AS value_{alias}
                            FROM read_parquet(?)
                            WHERE {' AND '.join(where)}
                        """
                        return cte_sql, [str(GOLD_PARQUET), *qparams]

                cte_a_sql, params_a = _build_source_cte(series_a, dimension_a, source_a, "a")
                cte_b_sql, params_b = _build_source_cte(series_b, dimension_b, source_b, "b")

                sql = f"""
                    WITH a AS (
                        {cte_a_sql}
                    ),
                    b AS (
                        {cte_b_sql}
                    )
                    SELECT value_a, value_b
                    FROM a JOIN b USING (date)
                    WHERE value_a IS NOT NULL AND value_b IS NOT NULL
                    ORDER BY date
                """
                rows = con.execute(sql, [*params_a, *params_b]).fetchall()
            finally:
                con.close()

            n = len(rows)
            if n < 2:
                return self.Output(
                    success=False,
                    error="Korelasyon icin en az iki ortak gozlem gereklidir.",
                    metric=params.metric,
                    selected_dimension_a=dimension_a,
                    selected_dimension_b=dimension_b,
                    n_observations=n,
                )

            xs = [row[0] for row in rows]
            ys = [row[1] for row in rows]
            mean_x = sum(xs) / n
            mean_y = sum(ys) / n
            numerator = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
            variance_x = sum((x - mean_x) ** 2 for x in xs)
            variance_y = sum((y - mean_y) ** 2 for y in ys)
            if variance_x == 0 or variance_y == 0:
                return self.Output(
                    success=False,
                    error="Korelasyon hesaplanamadi: serilerden en az birinin varyansi sifir.",
                    metric=params.metric,
                    selected_dimension_a=dimension_a,
                    selected_dimension_b=dimension_b,
                    n_observations=n,
                )

            corr = numerator / math.sqrt(variance_x * variance_y)
            return self.Output(
                success=True,
                metric=params.metric,
                selected_dimension_a=dimension_a,
                selected_dimension_b=dimension_b,
                correlation_coefficient=corr,
                n_observations=n,
                interpretation=(
                    "Bu sonuc Pearson korelasyon katsayisidir; iliski yonu ve gucunu "
                    "gosterir, tek basina nedensellik ispati degildir."
                ),
            )
        except Exception as exc:
            logger.exception("causality_check failed")
            return self.Output(success=False, error=str(exc), metric=params.metric)
