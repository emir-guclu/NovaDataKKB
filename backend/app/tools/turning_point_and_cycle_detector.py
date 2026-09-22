from __future__ import annotations

import logging
import unicodedata
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
from pydantic import BaseModel, Field, model_validator

from backend.app.services.chart_generator import generate_cycle_chart
from backend.app.services.inline_series import (
    DIMENSION_IGNORED_WARNING,
    EXACTLY_ONE_SOURCE_ERROR,
    OBSERVATIONS_DESCRIPTION,
    SERIES_ID_DESCRIPTION,
    SeriesLoadError,
    parse_inline_observations,
)
from backend.app.services.series_data_resolver import (
    ALIGNED_PARQUET,
    SILVER_DB,
    canonical_identifier,
    fetch_series_observations,
    resolve_series_location,
)
from backend.app.tools.base import BaseTool

logger = logging.getLogger(__name__)


def _canonical_identifier(value: str) -> str:
    return canonical_identifier(value)


def _resolve_series_id(con: duckdb.DuckDBPyConnection, input_id: str) -> str | None:
    sid, _ = resolve_series_location(con, input_id, ALIGNED_PARQUET, SILVER_DB)
    return sid


class TurningPointAndCycleDetectorTool(BaseTool):
    name = "turning_point_and_cycle_detector"
    description = (
        "Zaman serilerindeki makroekonomik döngüleri, dönüm noktalarını (yerel tepe/dip noktaları), "
        "genişleme ve daralma fazlarının sürelerini tespit eder ve görselleştirir. "
        "Kısa vadeli ani sıçramalar veya anomali tespiti için KULLANMA; onun için anomaly_detection kullanılmalıdır."
    )

    class Input(BaseModel):
        series_id: str | None = Field(default=None, description=SERIES_ID_DESCRIPTION)
        observations: list[dict] | None = Field(default=None, description=OBSERVATIONS_DESCRIPTION)
        dimension: str | None = Field(default=None, description="Seri boyutu (örn. Toplam)")
        smoothing_window: int = Field(default=3, ge=1, le=12, description="Yumuşatma penceresi (ay)")
        min_cycle_length: int = Field(default=4, ge=2, le=24, description="Minimum döngü uzunluğu (ay)")
        start_date: str | None = Field(default=None, description="Başlangıç tarihi (YYYY-MM-DD)")
        end_date: str | None = Field(default=None, description="Bitiş tarihi (YYYY-MM-DD)")

        @model_validator(mode="after")
        def _exactly_one_source(self):
            if bool(self.series_id) == bool(self.observations):
                raise ValueError(EXACTLY_ONE_SOURCE_ERROR)
            return self

    class Output(BaseModel):
        success: bool
        error: str | None = None
        series_id: str | None = None
        peaks: list[dict[str, Any]] = Field(default_factory=list)
        troughs: list[dict[str, Any]] = Field(default_factory=list)
        current_phase: str | None = None
        duration_months: int = 0
        max_drawdown_pct: float | None = None
        chart_url: str | None = None
        data_source: str | None = None
        warnings: list[str] = Field(default_factory=list)

    def _load_rows(self, params: Input) -> tuple[list[tuple[str, float | None]], str | None, str, list[str], str | None]:
        """Seriyi aligned parquet'ten veya satır içi gözlemlerden yükler.

        Döndürür: (satırlar[(tarih, değer)], seçilen dimension, data_source, uyarılar, çözülen series_id)
        """
        if params.observations:
            warnings: list[str] = []
            if params.dimension:
                warnings.append(DIMENSION_IGNORED_WARNING)
            try:
                rows, parse_warnings = parse_inline_observations(
                    params.observations, "value", params.start_date, params.end_date
                )
            except ValueError as exc:
                raise SeriesLoadError(str(exc), data_source="inline") from exc
            return rows, None, "inline", warnings + parse_warnings, None

        if not ALIGNED_PARQUET.exists():
            raise SeriesLoadError(f"Aligned parquet bulunamadi: {ALIGNED_PARQUET}")

        con = duckdb.connect()
        try:
            obs_dict, matched_id, dimension, err = fetch_series_observations(
                con, params.series_id, params.dimension,
                start_date=params.start_date, end_date=params.end_date,
                parquet_path=ALIGNED_PARQUET, silver_db_path=SILVER_DB,
            )
            if err or obs_dict is None:
                raise SeriesLoadError(err or f"Seri bulunamadi: {params.series_id}")

            rows = [(dt, val) for dt, val in obs_dict.items()]
        finally:
            con.close()
        return rows, dimension, "lakehouse", [], matched_id

    def run(self, params: Input) -> Output:
        try:
            try:
                rows, _dimension, data_source, warnings, matched_id = self._load_rows(params)
            except SeriesLoadError as exc:
                return self.Output(success=False, error=str(exc), data_source=exc.data_source)

            if len(rows) < 6:
                return self.Output(
                    success=False,
                    error=f"Döngü analizi için en az 6 gözlem gereklidir (bulunan: {len(rows)}).",
                    data_source=data_source,
                    warnings=warnings,
                )

            dates = [r[0] for r in rows if r[1] is not None]
            values = [float(r[1]) for r in rows if r[1] is not None]

            # Yumuşatma (rolling mean)
            w = params.smoothing_window
            if w > 1 and len(values) >= w:
                smoothed = np.convolve(values, np.ones(w) / w, mode="same")
            else:
                smoothed = np.array(values)

            # Bry-Boschan tarzı yerel ekstrema tespiti
            win = max(2, params.min_cycle_length // 2)
            n = len(smoothed)
            raw_peaks: list[int] = []
            raw_troughs: list[int] = []

            for i in range(win, n - win):
                local_window = smoothed[i - win : i + win + 1]
                if smoothed[i] == np.max(local_window) and np.sum(local_window == smoothed[i]) == 1:
                    raw_peaks.append(i)
                elif smoothed[i] == np.min(local_window) and np.sum(local_window == smoothed[i]) == 1:
                    raw_troughs.append(i)

            # Peak ve Trough listelerini kronolojik sırala ve ardışık tekerrürleri sadeleştir
            events: list[tuple[int, str]] = sorted(
                [(idx, "peak") for idx in raw_peaks] + [(idx, "trough") for idx in raw_troughs],
                key=lambda x: x[0],
            )

            filtered_events: list[tuple[int, str]] = []
            for idx, etype in events:
                if not filtered_events:
                    filtered_events.append((idx, etype))
                else:
                    last_idx, last_type = filtered_events[-1]
                    if last_type == etype:
                        if etype == "peak" and values[idx] > values[last_idx]:
                            filtered_events[-1] = (idx, etype)
                        elif etype == "trough" and values[idx] < values[last_idx]:
                            filtered_events[-1] = (idx, etype)
                    else:
                        filtered_events.append((idx, etype))

            peaks_idx = [idx for idx, etype in filtered_events if etype == "peak"]
            troughs_idx = [idx for idx, etype in filtered_events if etype == "trough"]

            # Max drawdown
            max_dd = 0.0
            peak_val = -float("inf")
            for val in values:
                if val > peak_val:
                    peak_val = val
                if peak_val > 0:
                    dd = ((peak_val - val) / peak_val) * 100.0
                    if dd > max_dd:
                        max_dd = dd

            # Mevcut Faz ve Süre
            if filtered_events:
                last_idx, last_type = filtered_events[-1]
                duration_months = (n - 1) - last_idx
                if last_type == "trough":
                    current_phase = "Genişleme / Toparlanma (Expansion)"
                else:
                    current_phase = "Daralma / Düzeltme (Contraction)"
            else:
                current_phase = "Stabil / Belirgin Döngü Yok"
                duration_months = n

            peaks_data = [{"date": dates[i], "value": round(values[i], 2)} for i in peaks_idx]
            troughs_data = [{"date": dates[i], "value": round(values[i], 2)} for i in troughs_idx]

            chart_url = generate_cycle_chart(
                dates=dates,
                values=values,
                peaks_indices=peaks_idx,
                troughs_indices=troughs_idx,
                title=f"{(matched_id or 'Satır İçi Seri').split(':')[-1]} Döngü ve Dönüm Noktaları Analizi",
            )

            return self.Output(
                success=True,
                series_id=matched_id,
                peaks=peaks_data,
                troughs=troughs_data,
                current_phase=current_phase,
                duration_months=duration_months,
                max_drawdown_pct=round(max_dd, 2),
                chart_url=chart_url,
                data_source=data_source,
                warnings=warnings,
            )

        except Exception as exc:
            logger.exception("turning_point_and_cycle_detector failed")
            return self.Output(success=False, error=str(exc))
