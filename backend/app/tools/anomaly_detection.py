from __future__ import annotations

import logging
import math
import unicodedata
from datetime import date, datetime
from pathlib import Path
from typing import Any, Literal

import duckdb
from pydantic import BaseModel, Field

from backend.app.tools.base import BaseTool

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
GOLD_PARQUET = PROJECT_ROOT / "data" / "gold" / "gold_periodic_change.parquet"


def _canonical_identifier(value: str) -> str:
    translation = str.maketrans({
        "ı": "i", "İ": "I", "ş": "s", "Ş": "S",
        "ğ": "g", "Ğ": "G", "ü": "u", "Ü": "U",
        "ö": "o", "Ö": "O", "ç": "c", "Ç": "C",
    })
    normalized = value.translate(translation)
    return unicodedata.normalize("NFKC", normalized).casefold()


def _json_ready(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


class AnomalyDetectionTool(BaseTool):
    name = "anomaly_detection"
    description = (
        "Tek bir finansal zaman serisinde z-score tabanli olagan disi yukselis "
        "veya dususleri bulur. Iki seri arasindaki iliski/korelasyon sorularinda "
        "KULLANMA; onun icin causality_check kullan. Ornek: "
        "series_id='BDDK_MONTHLY:tuketici_kredileri:tuketici_kredileri_konut', "
        "dimension='Toplam', metric='mom_pct_change'."
    )

    class Input(BaseModel):
        series_id: str = Field(description="Gold katmanindaki tam series_id")
        dimension: str | None = Field(
            default=None,
            description="Orn. Toplam, TP veya YP. Bos birakilirsa guvenli ise otomatik secilir.",
        )
        metric: Literal["value", "mom_abs_change", "mom_pct_change", "yoy_abs_change", "yoy_pct_change"] | str = Field(
            default="mom_pct_change",
            description="Anomali aranacak metrik",
        )
        start_date: str | None = Field(default=None, description="Opsiyonel baslangic tarihi, YYYY-MM-DD")
        end_date: str | None = Field(default=None, description="Opsiyonel bitis tarihi, YYYY-MM-DD")
        z_threshold: float = Field(default=2.0, gt=0, description="Mutlak z-score esigi")
        max_results: int = Field(default=20, ge=1, le=100, description="Donulecek maksimum anomali sayisi")

    class Output(BaseModel):
        success: bool
        error: str | None = None
        metric: str | None = None
        selected_dimension: str | None = None
        mean: float | None = None
        stddev: float | None = None
        n_observations: int = 0
        anomalies: list[dict[str, Any]] = Field(default_factory=list)

    def run(self, params: Input) -> Output:
        try:
            if not GOLD_PARQUET.exists():
                return self.Output(success=False, error=f"Gold parquet bulunamadi: {GOLD_PARQUET}")

            supported_metrics = {"value", "mom_abs_change", "mom_pct_change", "yoy_abs_change", "yoy_pct_change"}
            if params.metric not in supported_metrics:
                return self.Output(success=False, error=f"Metrik desteklenmiyor: {params.metric}", metric=params.metric)

            if bool(params.start_date) != bool(params.end_date):
                return self.Output(success=False, error="start_date ve end_date birlikte verilmelidir.", metric=params.metric)

            con = duckdb.connect()
            try:
                series_rows = con.execute(
                    "SELECT DISTINCT series_id FROM read_parquet(?)",
                    [str(GOLD_PARQUET)],
                ).fetchall()
                matched_series_id = next(
                    (
                        series_id
                        for (series_id,) in series_rows
                        if _canonical_identifier(series_id) == _canonical_identifier(params.series_id)
                    ),
                    None,
                )

                if matched_series_id is None:
                    return self.Output(
                        success=False,
                        error=f"Seri bulunamadi: {params.series_id}",
                        metric=params.metric,
                    )

                dims_rows = con.execute(
                    """
                    SELECT DISTINCT json_extract_string(dims, '$.variable') AS dimension
                    FROM read_parquet(?)
                    WHERE series_id = ?
                    ORDER BY dimension
                    """,
                    [str(GOLD_PARQUET), matched_series_id],
                ).fetchall()
                available_dims = [row[0] for row in dims_rows if row[0] is not None]

                dimension = params.dimension
                if dimension is None and available_dims:
                    if len(available_dims) == 1:
                        dimension = available_dims[0]
                    elif "Toplam" in available_dims:
                        dimension = "Toplam"
                    else:
                        return self.Output(
                            success=False,
                            error=f"Seri birden fazla dimension iceriyor. dimension belirtin: {available_dims}",
                            metric=params.metric,
                        )

                if dimension is not None and dimension not in available_dims:
                    return self.Output(
                        success=False,
                        error=f"Dimension bulunamadi: {dimension}. Mevcut dimensionlar: {available_dims}",
                        metric=params.metric,
                    )

                where_clauses = ["series_id = ?", f"{params.metric} IS NOT NULL"]
                query_params: list[str] = [matched_series_id]
                if dimension is None:
                    where_clauses.append("json_extract_string(dims, '$.variable') IS NULL")
                else:
                    where_clauses.append("json_extract_string(dims, '$.variable') = ?")
                    query_params.append(dimension)
                if params.start_date and params.end_date:
                    where_clauses.append("date BETWEEN ? AND ?")
                    query_params.extend([params.start_date, params.end_date])

                cursor = con.execute(
                    f"""
                    SELECT date, {params.metric} AS value
                    FROM read_parquet(?)
                    WHERE {' AND '.join(where_clauses)}
                    ORDER BY date
                    """,
                    [str(GOLD_PARQUET), *query_params],
                )
                rows = cursor.fetchall()
            finally:
                con.close()

            n = len(rows)
            if n < 2:
                return self.Output(
                    success=False,
                    error="Anomali hesabi icin en az iki gozlem gereklidir.",
                    metric=params.metric,
                    selected_dimension=dimension,
                    n_observations=n,
                )

            values = [row[1] for row in rows]
            mean = sum(values) / n
            stddev = math.sqrt(sum((value - mean) ** 2 for value in values) / (n - 1))
            if stddev == 0:
                return self.Output(
                    success=False,
                    error="Anomali hesaplanamadi: standart sapma sifir.",
                    metric=params.metric,
                    selected_dimension=dimension,
                    mean=mean,
                    stddev=stddev,
                    n_observations=n,
                )

            anomalies = []
            for row_date, value in rows:
                z_score = (value - mean) / stddev
                if abs(z_score) >= params.z_threshold:
                    anomalies.append(
                        {
                            "date": _json_ready(row_date),
                            "value": value,
                            "z_score": z_score,
                            "direction": "high" if z_score > 0 else "low",
                        }
                    )
            anomalies.sort(key=lambda row: abs(row["z_score"]), reverse=True)

            return self.Output(
                success=True,
                metric=params.metric,
                selected_dimension=dimension,
                mean=mean,
                stddev=stddev,
                n_observations=n,
                anomalies=anomalies[: params.max_results],
            )
        except Exception as exc:
            logger.exception("anomaly_detection failed")
            return self.Output(success=False, error=str(exc), metric=params.metric)
