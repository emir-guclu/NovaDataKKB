from __future__ import annotations

import logging
import math
import unicodedata
from datetime import date, datetime
from pathlib import Path
from typing import Any, Literal

import duckdb
from pydantic import BaseModel, Field, model_validator

from backend.app.services.inline_series import (
    DIMENSION_IGNORED_WARNING,
    EXACTLY_ONE_SOURCE_ERROR,
    OBSERVATIONS_DESCRIPTION,
    SERIES_ID_DESCRIPTION,
    SeriesLoadError,
    parse_inline_observations,
)
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


def _canonical_identifier(value: str) -> str:
    return canonical_identifier(value)


def _json_ready(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


class AnomalyDetectionTool(BaseTool):
    name = "anomaly_detection"
    description = (
        "Zaman serisindeki istatistiksel uclari (aylik/yillik soklar veya "
        "mevsimsellik disi hareketler) IQR ve z-score hibrit yontemi ile tespit eder. "
        "Genel trend veya ham veri okumak icin KULLANMA; onun icin change_detection "
        "kullan. Ornek: konut kredisi aylik degisim soklari icin "
        "series_id='BDDK_MONTHLY:tuketici_kredileri:tuketici_kredileri_konut', "
        "dimension='Toplam', metric='mom_pct_change'."
    )

    class Input(BaseModel):
        series_id: str | None = Field(default=None, description=SERIES_ID_DESCRIPTION)
        observations: list[dict] | None = Field(default=None, description=OBSERVATIONS_DESCRIPTION)
        dimension: str | None = Field(
            default=None,
            description="Orn. Toplam, TP veya YP. Bos birakilirsa guvenli ise otomatik secilir.",
        )
        metric: Literal["value", "mom_abs_change", "mom_pct_change", "yoy_abs_change", "yoy_pct_change"] | str = Field(
            default="mom_pct_change",
            description="Anomali tespiti yapilacak metrik",
        )
        start_date: str | None = Field(default=None, description="Opsiyonel baslangic tarihi, YYYY-MM-DD")
        end_date: str | None = Field(default=None, description="Opsiyonel bitis tarihi, YYYY-MM-DD")
        z_threshold: float = Field(default=2.0, gt=0, description="Mutlak z-score esigi")
        max_results: int = Field(default=20, ge=1, le=100, description="Donulecek maksimum anomali sayisi")

        @model_validator(mode="after")
        def _exactly_one_source(self):
            if bool(self.series_id) == bool(self.observations):
                raise ValueError(EXACTLY_ONE_SOURCE_ERROR)
            return self

    class Output(BaseModel):
        success: bool
        error: str | None = None
        metric: str | None = None
        selected_dimension: str | None = None
        mean: float | None = None
        stddev: float | None = None
        n_observations: int = 0
        anomalies: list[dict[str, Any]] = Field(default_factory=list)
        data_source: str | None = None
        warnings: list[str] = Field(default_factory=list)

    def _load_series(self, params: Input) -> tuple[list[tuple[Any, float]], str | None, str, list[str]]:
        """Seriyi lakehouse'tan veya satır içi gözlemlerden yükler.

        Döndürür: (satırlar[(tarih, değer)], seçilen dimension, data_source, uyarılar)
        """
        if params.observations:
            warnings: list[str] = []
            if params.dimension:
                warnings.append(DIMENSION_IGNORED_WARNING)
            try:
                rows, parse_warnings = parse_inline_observations(
                    params.observations, params.metric, params.start_date, params.end_date
                )
            except ValueError as exc:
                raise SeriesLoadError(str(exc), data_source="inline") from exc
            return rows, None, "inline", warnings + parse_warnings

        if not GOLD_PARQUET.exists():
            raise SeriesLoadError(f"Gold parquet bulunamadi: {GOLD_PARQUET}")

        supported_metrics = {"value", "mom_abs_change", "mom_pct_change", "yoy_abs_change", "yoy_pct_change"}
        if params.metric not in supported_metrics:
            raise SeriesLoadError(f"Metrik desteklenmiyor: {params.metric}")

        if bool(params.start_date) != bool(params.end_date):
            raise SeriesLoadError("start_date ve end_date birlikte verilmelidir.")

        con = duckdb.connect()
        try:
            matched_series_id, source = resolve_series_location(
                con, params.series_id, GOLD_PARQUET, SILVER_DB
            )
            if not matched_series_id or not source:
                raise SeriesLoadError(f"Seri bulunamadi: {params.series_id}")

            available_dims = get_available_dimensions(con, matched_series_id, source, GOLD_PARQUET)
            dimension, dim_err = resolve_dimension(available_dims, params.dimension)
            if dim_err:
                raise SeriesLoadError(dim_err)

            if source == "silver":
                create_silver_periodic_view(con, "silver_anomaly_view", matched_series_id, dimension)
                where_clauses = [f"{params.metric} IS NOT NULL"]
                query_params: list[Any] = []
                if params.start_date and params.end_date:
                    where_clauses.append("date BETWEEN ? AND ?")
                    query_params.extend([params.start_date, params.end_date])
                cursor = con.execute(
                    f"""
                    SELECT date, {params.metric} AS value
                    FROM silver_anomaly_view
                    WHERE {' AND '.join(where_clauses)}
                    ORDER BY date
                    """,
                    query_params,
                )
                rows = cursor.fetchall()
            else:
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
        return rows, dimension, "lakehouse", []

    def run(self, params: Input) -> Output:
        try:
            try:
                rows, dimension, data_source, warnings = self._load_series(params)
            except SeriesLoadError as exc:
                return self.Output(
                    success=False, error=str(exc), metric=params.metric, data_source=exc.data_source
                )

            n = len(rows)
            if n < 2:
                return self.Output(
                    success=False,
                    error="Anomali hesabi icin en az iki gozlem gereklidir.",
                    metric=params.metric,
                    selected_dimension=dimension,
                    n_observations=n,
                    data_source=data_source,
                    warnings=warnings,
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
                    data_source=data_source,
                    warnings=warnings,
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
                data_source=data_source,
                warnings=warnings,
            )
        except Exception as exc:
            logger.exception("anomaly_detection failed")
            return self.Output(success=False, error=str(exc), metric=params.metric)
