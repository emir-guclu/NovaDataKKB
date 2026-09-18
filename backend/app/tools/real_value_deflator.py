from __future__ import annotations

import logging
import unicodedata
from pathlib import Path
from typing import Any

import duckdb
from pydantic import BaseModel, Field

from backend.app.services.chart_generator import generate_deflator_chart
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


class RealValueDeflatorTool(BaseTool):
    name = "real_value_deflator"
    description = (
        "Nominal finansal serileri (kredi, mevduat, varlık vb.) TÜFE enflasyonundan arındırarak "
        "reel büyüme oranını, enflasyon erozyonunu (satın alma gücü kaybı) ve alan grafiğini üretir. "
        "Ham nominal değişimleri veya korelasyonu incelemek için KULLANMA; onlar için change_detection veya "
        "causality_check kullanılmalıdır. Örnek nominal_series_id: "
        "'BDDK_MONTHLY:tuketici_kredileri:tuketici_kredileri_konut', deflator_series_id: 'TP.GENENDEKS.T1'."
    )

    class Input(BaseModel):
        nominal_series_id: str = Field(description="Enflasyondan arındırılacak serinin ID'si")
        deflator_series_id: str = Field(
            default="TP.GENENDEKS.T1",
            description="Deflatör serisi (varsayılan: TÜFE / TP.GENENDEKS.T1)",
        )
        dimension: str | None = Field(
            default=None,
            description="Seri boyutu (örn: Toplam, TP, YP). Belirtilmezse otomatik seçilir.",
        )
        base_date: str | None = Field(
            default=None,
            description="Baz tarih (YYYY-MM-DD). Belirtilmezse dönemin ilk tarihi baz alınır.",
        )
        start_date: str | None = Field(default=None, description="Başlangıç tarihi (YYYY-MM-DD)")
        end_date: str | None = Field(default=None, description="Bitiş tarihi (YYYY-MM-DD)")

    class Output(BaseModel):
        success: bool
        error: str | None = None
        nominal_series_id: str | None = None
        deflator_series_id: str | None = None
        nominal_growth_pct: float | None = None
        inflation_pct: float | None = None
        real_growth_pct: float | None = None
        erosion_amount: float | None = None
        summary_verdict: str | None = None
        chart_url: str | None = None
        data_points: list[dict[str, Any]] = Field(default_factory=list)

    def run(self, params: Input) -> Output:
        try:
            if not ALIGNED_PARQUET.exists():
                return self.Output(success=False, error=f"Aligned parquet bulunamadi: {ALIGNED_PARQUET}")

            con = duckdb.connect()
            try:
                nom_dict, nom_id, dimension, nom_err = fetch_series_observations(
                    con, params.nominal_series_id, params.dimension,
                    start_date=params.start_date, end_date=params.end_date,
                    parquet_path=ALIGNED_PARQUET, silver_db_path=SILVER_DB,
                )
                if nom_err or not nom_dict:
                    return self.Output(
                        success=False,
                        error=f"Nominal seri bulunamadi: {params.nominal_series_id}"
                        if not nom_err or "Seri bulunamadi" in nom_err
                        else nom_err,
                    )

                def_dict, def_id, _, def_err = fetch_series_observations(
                    con, params.deflator_series_id,
                    start_date=params.start_date, end_date=params.end_date,
                    parquet_path=ALIGNED_PARQUET, silver_db_path=SILVER_DB,
                )
                if def_err or not def_dict:
                    return self.Output(
                        success=False,
                        error=f"Deflatör serisi bulunamadi: {params.deflator_series_id}"
                        if not def_err or "Seri bulunamadi" in def_err
                        else def_err,
                    )
            finally:
                con.close()

            common_dates = sorted(set(nom_dict.keys()) & set(def_dict.keys()))
            if len(common_dates) < 2:
                return self.Output(
                    success=False,
                    error="Analiz için yeterli ortak tarihli veri noktası bulunamadı.",
                )

            # Baz tarih CPI
            base_date = params.base_date if params.base_date in def_dict else common_dates[0]
            base_cpi = def_dict[base_date]

            data_points = []
            dates_list = []
            nominal_vals = []
            real_vals = []

            for dt in common_dates:
                n_val = nom_dict[dt]
                c_val = def_dict[dt]
                r_val = n_val * (base_cpi / c_val) if c_val > 0 else n_val

                dates_list.append(dt)
                nominal_vals.append(round(n_val, 2))
                real_vals.append(round(r_val, 2))

                data_points.append({
                    "date": dt,
                    "nominal_value": round(n_val, 2),
                    "deflator_value": round(c_val, 2),
                    "real_value": round(r_val, 2),
                })

            start_nom = nominal_vals[0]
            end_nom = nominal_vals[-1]
            start_def = def_dict[common_dates[0]]
            end_def = def_dict[common_dates[-1]]

            nom_growth = ((end_nom - start_nom) / start_nom) * 100 if start_nom > 0 else 0.0
            inf_pct = ((end_def - start_def) / start_def) * 100 if start_def > 0 else 0.0
            real_growth = (((1 + nom_growth / 100.0) / (1 + inf_pct / 100.0)) - 1.0) * 100.0
            erosion = round(end_nom - real_vals[-1], 2)

            direction = "reel büyüme" if real_growth >= 0 else "reel daralma (küçülme)"
            verdict = (
                f"İncelenen dönemde ({common_dates[0]} - {common_dates[-1]}), nominal büyüme %{nom_growth:.2f} "
                f"iken enflasyon %{inf_pct:.2f} olarak gerçekleşti. "
                f"Buna bağlı olarak seri %{abs(real_growth):.2f} oranında {direction} kaydetti. "
                f"Enflasyon kaynaklı satın alma gücü erozyonu yaklaşık {erosion:,.2f} birimdir."
            )

            chart_url = generate_deflator_chart(
                dates=dates_list,
                nominal_values=nominal_vals,
                real_values=real_vals,
                series_name=nom_id.split(":")[-1],
                unit="Birim",
            )

            return self.Output(
                success=True,
                nominal_series_id=nom_id,
                deflator_series_id=def_id,
                nominal_growth_pct=round(nom_growth, 2),
                inflation_pct=round(inf_pct, 2),
                real_growth_pct=round(real_growth, 2),
                erosion_amount=erosion,
                summary_verdict=verdict,
                chart_url=chart_url,
                data_points=data_points,
            )

        except Exception as exc:
            logger.exception("real_value_deflator failed")
            return self.Output(success=False, error=str(exc))
