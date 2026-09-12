from __future__ import annotations

import logging
import math
import unicodedata
from pathlib import Path
from typing import Literal

import duckdb
from pydantic import BaseModel, Field

from backend.app.tools.base import BaseTool

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
GOLD_PARQUET = PROJECT_ROOT / "data" / "gold" / "gold_periodic_change.parquet"
SUPPORTED_METRICS = {"value", "mom_abs_change", "mom_pct_change", "yoy_abs_change", "yoy_pct_change"}


def _canonical_identifier(value: str) -> str:
    translation = str.maketrans({
        "ı": "i", "İ": "I", "ş": "s", "Ş": "S",
        "ğ": "g", "Ğ": "G", "ü": "u", "Ü": "U",
        "ö": "o", "Ö": "O", "ç": "c", "Ç": "C",
    })
    normalized = value.translate(translation)
    return unicodedata.normalize("NFKC", normalized).casefold()


def _resolve_series_and_dimension(
    con: duckdb.DuckDBPyConnection,
    requested_series_id: str,
    requested_dimension: str | None,
) -> tuple[str | None, str | None, str | None]:
    series_rows = con.execute(
        "SELECT DISTINCT series_id FROM read_parquet(?)",
        [str(GOLD_PARQUET)],
    ).fetchall()
    matched_series_id = next(
        (
            series_id
            for (series_id,) in series_rows
            if _canonical_identifier(series_id) == _canonical_identifier(requested_series_id)
        ),
        None,
    )
    if matched_series_id is None:
        return None, None, f"Seri bulunamadi: {requested_series_id}"

    dims_rows = con.execute(
        """
        SELECT DISTINCT json_extract_string(dims, '$.variable') AS dimension
        FROM read_parquet(?)
        WHERE series_id = ?
        ORDER BY dimension
        """,
        [str(GOLD_PARQUET), matched_series_id],
    ).fetchall()
    available_dims = [row[0] for row in dims_rows]

    dimension = requested_dimension
    non_null_dims = [dim for dim in available_dims if dim is not None]
    if dimension is None and non_null_dims:
        if len(non_null_dims) == 1:
            dimension = non_null_dims[0]
        elif "Toplam" in non_null_dims:
            dimension = "Toplam"
        else:
            return (
                matched_series_id,
                None,
                f"Seri birden fazla dimension iceriyor. dimension belirtin: {non_null_dims}",
            )

    if dimension is not None and dimension not in non_null_dims:
        return (
            matched_series_id,
            None,
            f"Dimension bulunamadi: {dimension}. Mevcut dimensionlar: {non_null_dims}",
        )

    return matched_series_id, dimension, None


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
                series_a, dimension_a, error = _resolve_series_and_dimension(
                    con, params.series_id_a, params.dimension_a
                )
                if error:
                    return self.Output(success=False, error=error, metric=params.metric)

                series_b, dimension_b, error = _resolve_series_and_dimension(
                    con, params.series_id_b, params.dimension_b
                )
                if error:
                    return self.Output(success=False, error=error, metric=params.metric)

                where_a = ["series_id = ?"]
                where_b = ["series_id = ?"]
                params_a: list[str | None] = [series_a]
                params_b: list[str | None] = [series_b]

                if dimension_a is None:
                    where_a.append("json_extract_string(dims, '$.variable') IS NULL")
                else:
                    where_a.append("json_extract_string(dims, '$.variable') = ?")
                    params_a.append(dimension_a)

                if dimension_b is None:
                    where_b.append("json_extract_string(dims, '$.variable') IS NULL")
                else:
                    where_b.append("json_extract_string(dims, '$.variable') = ?")
                    params_b.append(dimension_b)

                if params.start_date and params.end_date:
                    where_a.append("date BETWEEN ? AND ?")
                    where_b.append("date BETWEEN ? AND ?")
                    params_a.extend([params.start_date, params.end_date])
                    params_b.extend([params.start_date, params.end_date])

                sql = f"""
                    WITH a AS (
                        SELECT date, {params.metric} AS value_a
                        FROM read_parquet(?)
                        WHERE {' AND '.join(where_a)}
                    ),
                    b AS (
                        SELECT date, {params.metric} AS value_b
                        FROM read_parquet(?)
                        WHERE {' AND '.join(where_b)}
                    )
                    SELECT value_a, value_b
                    FROM a JOIN b USING (date)
                    WHERE value_a IS NOT NULL AND value_b IS NOT NULL
                    ORDER BY date
                """
                rows = con.execute(sql, [str(GOLD_PARQUET), *params_a, str(GOLD_PARQUET), *params_b]).fetchall()
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
