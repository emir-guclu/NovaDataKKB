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
from backend.app.tools.base import BaseTool

logger = logging.getLogger(__name__)


def _canonical_identifier(value: str) -> str:
    translation = str.maketrans({
        "ı": "i", "İ": "I", "ş": "s", "Ş": "S",
        "ğ": "g", "Ğ": "G", "ü": "u", "Ü": "U",
        "ö": "o", "Ö": "O", "ç": "c", "Ç": "C",
    })
    normalized = value.translate(translation)
    return unicodedata.normalize("NFKC", normalized).casefold()


PROJECT_ROOT = Path(__file__).resolve().parents[3]
GOLD_PARQUET = PROJECT_ROOT / "data" / "gold" / "gold_periodic_change.parquet"


class ChangeDetectionTool(BaseTool):
    name = "change_detection"
    description = (
        "Bir finansal serinin aylik (MoM) veya yillik (YoY) degisimini gercek "
        "gold_periodic_change verisinden getirir. Ham degeri veya guncel haberleri "
        "aramak icin KULLANMA. Tarih verilmezse en guncel gozlemi getirir. "
        "Ornek: konut kredisi hacmi icin "
        "series_id='BDDK_MONTHLY:tuketici_kredileri:tuketici_kredileri_konut' "
        "ve dimension='Toplam' kullan."
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
            series_rows = con.execute(
                "SELECT DISTINCT series_id FROM read_parquet(?)",
                [str(GOLD_PARQUET)],
            ).fetchall()
            available_series = [row[0] for row in series_rows]

            canonical_requested = _canonical_identifier(params.series_id)
            matched_series_id = next(
                (
                    series_id
                    for series_id in available_series
                    if _canonical_identifier(series_id) == canonical_requested
                ),
                None,
            )

            if matched_series_id is None:
                raise SeriesLoadError(f"Seri bulunamadi: {params.series_id}")

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
            if not available_dims:
                raise SeriesLoadError(f"Seri bulunamadi: {params.series_id}")

            dimension = params.dimension
            if dimension is None:
                if len(available_dims) == 1:
                    dimension = available_dims[0]
                elif "Toplam" in available_dims:
                    dimension = "Toplam"
                else:
                    raise SeriesLoadError(
                        "Seri birden fazla dimension iceriyor. "
                        f"dimension belirtin: {available_dims}"
                    )

            if dimension not in available_dims:
                raise SeriesLoadError(
                    f"Dimension bulunamadi: {dimension}. "
                    f"Mevcut dimensionlar: {available_dims}"
                )

            if params.start_date and params.end_date:
                sql = """
                    SELECT date, value, mom_abs_change, mom_pct_change,
                           yoy_abs_change, yoy_pct_change, source, nature, unit, dims
                    FROM read_parquet(?)
                    WHERE series_id = ?
                      AND json_extract_string(dims, '$.variable') = ?
                      AND date BETWEEN ? AND ?
                    ORDER BY date
                """
                query_params = [str(GOLD_PARQUET), matched_series_id, dimension, params.start_date, params.end_date]
            else:
                sql = """
                    SELECT date, value, mom_abs_change, mom_pct_change,
                           yoy_abs_change, yoy_pct_change, source, nature, unit, dims
                    FROM read_parquet(?)
                    WHERE series_id = ?
                      AND json_extract_string(dims, '$.variable') = ?
                    ORDER BY date DESC
                    LIMIT 1
                """
                query_params = [str(GOLD_PARQUET), matched_series_id, dimension]

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
