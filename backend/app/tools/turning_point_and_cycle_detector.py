from __future__ import annotations

import logging
import unicodedata
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
from pydantic import BaseModel, Field

from backend.app.services.chart_generator import generate_cycle_chart
from backend.app.tools.base import BaseTool

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
ALIGNED_PARQUET = PROJECT_ROOT / "data" / "aligned" / "monthly" / "observations.parquet"


def _canonical_identifier(value: str) -> str:
    translation = str.maketrans({
        "ı": "i", "İ": "I", "ş": "s", "Ş": "S",
        "ğ": "g", "Ğ": "G", "ü": "u", "Ü": "U",
        "ö": "o", "Ö": "O", "ç": "c", "Ç": "C",
    })
    normalized = value.translate(translation)
    return unicodedata.normalize("NFKC", normalized).casefold()


def _resolve_series_id(con: duckdb.DuckDBPyConnection, input_id: str) -> str | None:
    canonical = _canonical_identifier(input_id)
    rows = con.execute("SELECT DISTINCT series_id FROM read_parquet(?)", [str(ALIGNED_PARQUET)]).fetchall()
    all_ids = [r[0] for r in rows]

    for sid in all_ids:
        if _canonical_identifier(sid) == canonical:
            return sid
        if sid.endswith(input_id) or input_id.endswith(sid):
            return sid
    return None


class TurningPointAndCycleDetectorTool(BaseTool):
    name = "turning_point_and_cycle_detector"
    description = (
        "Zaman serilerindeki makroekonomik döngüleri, dönüm noktalarını (yerel tepe/dip noktaları), "
        "genişleme ve daralma fazlarının sürelerini tespit eder ve görselleştirir. "
        "Kısa vadeli ani sıçramalar veya anomali tespiti için KULLANMA; onun için anomaly_detection kullanılmalıdır. "
        "Örnek series_id: 'BDDK_MONTHLY:tuketici_kredileri:tuketici_kredileri_konut', dimension: 'Toplam'."
    )

    class Input(BaseModel):
        series_id: str = Field(description="Zaman serisi ID'si")
        dimension: str | None = Field(default=None, description="Seri boyutu (örn. Toplam)")
        smoothing_window: int = Field(default=3, ge=1, le=12, description="Yumuşatma penceresi (ay)")
        min_cycle_length: int = Field(default=4, ge=2, le=24, description="Minimum döngü uzunluğu (ay)")
        start_date: str | None = Field(default=None, description="Başlangıç tarihi (YYYY-MM-DD)")
        end_date: str | None = Field(default=None, description="Bitiş tarihi (YYYY-MM-DD)")

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

    def run(self, params: Input) -> Output:
        try:
            if not ALIGNED_PARQUET.exists():
                return self.Output(success=False, error=f"Aligned parquet bulunamadi: {ALIGNED_PARQUET}")

            con = duckdb.connect()
            try:
                matched_id = _resolve_series_id(con, params.series_id)
                if not matched_id:
                    return self.Output(success=False, error=f"Seri bulunamadi: {params.series_id}")

                dim_rows = con.execute(
                    """
                    SELECT DISTINCT json_extract_string(dims, '$.variable') AS dimension
                    FROM read_parquet(?)
                    WHERE series_id = ?
                    """,
                    [str(ALIGNED_PARQUET), matched_id],
                ).fetchall()
                available_dims = [r[0] for r in dim_rows if r[0] is not None]

                dimension = params.dimension
                if dimension is None:
                    if len(available_dims) == 1:
                        dimension = available_dims[0]
                    elif "Toplam" in available_dims:
                        dimension = "Toplam"
                    elif available_dims:
                        dimension = available_dims[0]

                where_clauses = ["series_id = ?"]
                query_params: list[Any] = [matched_id]
                if dimension:
                    where_clauses.append("json_extract_string(dims, '$.variable') = ?")
                    query_params.append(dimension)

                if params.start_date:
                    where_clauses.append("date >= ?")
                    query_params.append(params.start_date)
                if params.end_date:
                    where_clauses.append("date <= ?")
                    query_params.append(params.end_date)

                sql = f"""
                    SELECT strftime(date, '%Y-%m-%d') as dt, value
                    FROM read_parquet(?)
                    WHERE {" AND ".join(where_clauses)}
                    ORDER BY date
                """
                rows = con.execute(sql, [str(ALIGNED_PARQUET), *query_params]).fetchall()
            finally:
                con.close()

            if len(rows) < 6:
                return self.Output(
                    success=False,
                    error=f"Döngü analizi için en az 6 gözlem gereklidir (bulunan: {len(rows)}).",
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
                title=f"{matched_id.split(':')[-1]} Döngü ve Dönüm Noktaları Analizi",
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
            )

        except Exception as exc:
            logger.exception("turning_point_and_cycle_detector failed")
            return self.Output(success=False, error=str(exc))
