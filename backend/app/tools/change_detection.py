from __future__ import annotations

import logging
import unicodedata
from pathlib import Path
from typing import Any

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


class ChangeDetectionTool(BaseTool):
    name = "change_detection"
    description = (
        "Bir finansal serinin aylik (MoM) veya yillik (YoY) degisimini gercek "
        "gold_periodic_change verisinden getirir. Ham degeri veya guncel haberleri "
        "aramak icin KULLANMA. Tarih verilmezse en guncel gozlemi getirir."
    )

    class Input(BaseModel):
        series_id: str | None = Field(default=None, description=SERIES_ID_DESCRIPTION)
        observations: list[dict] | None = Field(default=None, description=OBSERVATIONS_DESCRIPTION)
        dimension: str | None = Field(
            default=None,
            description="Orn. Toplam, TP veya YP. Bos birakilirsa guvenli ise otomatik secilir.",
        )
        start_date: str | None = Field(
            default=None,
            description="Opsiyonel baslangic tarihi, YYYY-MM-DD",
        )
        end_date: str | None = Field(
            default=None,
            description="Opsiyonel bitis tarihi, YYYY-MM-DD",
        )

        @model_validator(mode="after")
        def _exactly_one_source(self):
            if bool(self.series_id) == bool(self.observations):
                raise ValueError(EXACTLY_ONE_SOURCE_ERROR)
            return self

    class Output(BaseModel):
        success: bool
        error: str | None = None
        selected_dimension: str | None = None
        rows: list[dict[str, Any]] = Field(default_factory=list)
        data_source: str | None = None
        warnings: list[str] = Field(default_factory=list)

    def _load_rows(self, params: Input) -> tuple[list[dict[str, Any]], str | None, str, list[str]]:
        """Satırları lakehouse'tan veya satır içi gözlemlerden yükler.

        Döndürür: (satırlar[dict], seçilen dimension, data_source, uyarılar)
        """
        if params.observations:
            warnings: list[str] = []
            if params.dimension:
                warnings.append(DIMENSION_IGNORED_WARNING)
            try:
                values, value_warnings = parse_inline_observations(
                    params.observations, "value", params.start_date, params.end_date
                )
                changes, change_warnings = parse_inline_observations(
                    params.observations, "mom_pct_change", params.start_date, params.end_date
                )
            except ValueError as exc:
                raise SeriesLoadError(str(exc), data_source="inline") from exc
            change_by_date = dict(changes)
            rows = [
                {"date": row_date, "value": value, "mom_pct_change": change_by_date.get(row_date)}
                for row_date, value in values
            ]
            if not (params.start_date and params.end_date):
                rows = rows[-1:]  # tarih verilmezse lakehouse dalı gibi en güncel gözlem
            return rows, None, "inline", warnings + value_warnings + [
                w for w in change_warnings if w not in value_warnings
            ]

        if not GOLD_PARQUET.exists():
            raise SeriesLoadError(f"Gold parquet bulunamadi: {GOLD_PARQUET}")

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
                create_silver_periodic_view(con, "silver_change_view", matched_series_id, dimension)
                where = []
                query_params: list[Any] = []
                if params.start_date and params.end_date:
                    where.append("date BETWEEN ? AND ?")
                    query_params.extend([params.start_date, params.end_date])
                where_clause = f"WHERE {' AND '.join(where)}" if where else ""
                order_limit = "ORDER BY date" if (params.start_date and params.end_date) else "ORDER BY date DESC LIMIT 1"
                sql = f"""
                    SELECT date, value, mom_abs_change, mom_pct_change,
                           yoy_abs_change, yoy_pct_change, source, nature, unit, dims
                    FROM silver_change_view
                    {where_clause}
                    {order_limit}
                """
                cursor = con.execute(sql, query_params)
            else:
                dim_filter = "json_extract_string(dims, '$.variable') = ?" if dimension else "json_extract_string(dims, '$.variable') IS NULL"
                dim_params = [dimension] if dimension else []
                if params.start_date and params.end_date:
                    sql = f"""
                        SELECT date, value, mom_abs_change, mom_pct_change,
                               yoy_abs_change, yoy_pct_change, source, nature, unit, dims
                        FROM read_parquet(?)
                        WHERE series_id = ?
                          AND {dim_filter}
                          AND date BETWEEN ? AND ?
                        ORDER BY date
                    """
                    query_params = [str(GOLD_PARQUET), matched_series_id, *dim_params, params.start_date, params.end_date]
                else:
                    sql = f"""
                        SELECT date, value, mom_abs_change, mom_pct_change,
                               yoy_abs_change, yoy_pct_change, source, nature, unit, dims
                        FROM read_parquet(?)
                        WHERE series_id = ?
                          AND {dim_filter}
                        ORDER BY date DESC
                        LIMIT 1
                    """
                    query_params = [str(GOLD_PARQUET), matched_series_id, *dim_params]

                cursor = con.execute(sql, query_params)

            columns = [col[0] for col in cursor.description]
            raw_rows = cursor.fetchall()
        finally:
            con.close()
        rows = [dict(zip(columns, row)) for row in raw_rows]
        return rows, dimension, "lakehouse", []

    def run(self, params: Input) -> Output:
        try:
            try:
                rows, dimension, data_source, warnings = self._load_rows(params)
            except SeriesLoadError as exc:
                return self.Output(success=False, error=str(exc), data_source=exc.data_source)

            if not rows:
                return self.Output(
                    success=False,
                    error="Belirtilen filtreler icin veri bulunamadi.",
                    selected_dimension=dimension,
                    data_source=data_source,
                    warnings=warnings,
                )

            return self.Output(
                success=True,
                selected_dimension=dimension,
                rows=rows,
                data_source=data_source,
                warnings=warnings,
            )
        except Exception as exc:
            logger.exception("change_detection failed")
            return self.Output(success=False, error=str(exc))
