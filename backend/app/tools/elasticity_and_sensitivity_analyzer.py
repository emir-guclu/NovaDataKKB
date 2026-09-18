from __future__ import annotations

import logging
import unicodedata
from pathlib import Path
from typing import Any, Literal

import duckdb
import numpy as np
from pydantic import BaseModel, Field

from backend.app.services.chart_generator import generate_elasticity_chart
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


class ElasticityAndSensitivityAnalyzerTool(BaseTool):
    name = "elasticity_and_sensitivity_analyzer"
    description = (
        "İki finansal değişken arasındaki esneklik katsayısını (elasticity) ve duyarlılığı hesaplar "
        "(örn. Faiz artışının konut/tüketici kredisi talebine etkisi). OLS log-log regresyon veya "
        "arc elasticity ile saçılım ve trend grafiği üretir. Doğrudan nedensellik veya anomali tespiti için KULLANMA; "
        "onun için causality_check veya anomaly_detection kullanılmalıdır. Örnek: dependent_series_id: "
        "'BDDK_MONTHLY:tuketici_kredileri:tuketici_kredileri_konut', independent_series_id: 'EVDS:TP.GENENDEKS.T1'."
    )

    class Input(BaseModel):
        dependent_series_id: str = Field(description="Bağımlı değişken serisi (örn. Konut Kredisi)")
        independent_series_id: str = Field(description="Bağımsız değişken serisi (örn. Politika Faizi / TÜFE)")
        dependent_dimension: str | None = Field(default=None, description="Bağımlı değişken boyutu (örn: Toplam)")
        independent_dimension: str | None = Field(default=None, description="Bağımsız değişken boyutu")
        lag_months: int = Field(default=0, ge=0, le=24, description="Gecikme süresi (ay cinsinden)")
        method: Literal["arc_elasticity", "log_log_regression"] = Field(
            default="log_log_regression",
            description="Hesaplama metodu ('log_log_regression' veya 'arc_elasticity')",
        )
        start_date: str | None = Field(default=None, description="Başlangıç tarihi (YYYY-MM-DD)")
        end_date: str | None = Field(default=None, description="Bitiş tarihi (YYYY-MM-DD)")

    class Output(BaseModel):
        success: bool
        error: str | None = None
        dependent_series_id: str | None = None
        independent_series_id: str | None = None
        method: str | None = None
        elasticity_coefficient: float | None = None
        r_squared: float | None = None
        classification: str | None = None
        interpretation: str | None = None
        chart_url: str | None = None
        sample_size: int = 0

    def run(self, params: Input) -> Output:
        try:
            if not ALIGNED_PARQUET.exists():
                return self.Output(success=False, error=f"Aligned parquet bulunamadi: {ALIGNED_PARQUET}")

            con = duckdb.connect()
            try:
                dep_data, dep_id, dep_dim, dep_err = fetch_series_observations(
                    con, params.dependent_series_id, params.dependent_dimension,
                    parquet_path=ALIGNED_PARQUET, silver_db_path=SILVER_DB,
                )
                if dep_err or not dep_data:
                    return self.Output(
                        success=False,
                        error=f"Bagimli seri bulunamadi: {params.dependent_series_id}"
                        if not dep_err or "Seri bulunamadi" in dep_err
                        else dep_err,
                    )

                indep_data, indep_id, indep_dim, indep_err = fetch_series_observations(
                    con, params.independent_series_id, params.independent_dimension,
                    parquet_path=ALIGNED_PARQUET, silver_db_path=SILVER_DB,
                )
                if indep_err or not indep_data:
                    return self.Output(
                        success=False,
                        error=f"Bagimsiz seri bulunamadi: {params.independent_series_id}"
                        if not indep_err or "Seri bulunamadi" in indep_err
                        else indep_err,
                    )
            finally:
                con.close()

            # Tarihleri sırala ve gecikmeyi (lag) uygula
            sorted_dates = sorted(set(dep_data.keys()))
            if params.start_date:
                sorted_dates = [d for d in sorted_dates if d >= params.start_date]
            if params.end_date:
                sorted_dates = [d for d in sorted_dates if d <= params.end_date]

            # Lag: bağımsız değişken t-k zamanındaki değeri
            indep_dates = sorted(set(indep_data.keys()))
            date_to_idx = {d: i for i, d in enumerate(indep_dates)}

            paired_x: list[float] = []
            paired_y: list[float] = []

            for dt in sorted_dates:
                if dt not in date_to_idx:
                    continue
                cur_idx = date_to_idx[dt]
                lag_idx = cur_idx - params.lag_months
                if 0 <= lag_idx < len(indep_dates):
                    lag_dt = indep_dates[lag_idx]
                    x_val = indep_data[lag_dt]
                    y_val = dep_data[dt]
                    paired_x.append(x_val)
                    paired_y.append(y_val)

            if len(paired_x) < 3:
                return self.Output(
                    success=False,
                    error=f"Yeterli gözlem sayısı bulunamadı (mevcut: {len(paired_x)}).",
                )

            x_arr = np.array(paired_x, dtype=float)
            y_arr = np.array(paired_y, dtype=float)

            beta: float = 0.0
            r_sq: float = 0.0

            if params.method == "log_log_regression":
                if np.all(x_arr > 0) and np.all(y_arr > 0):
                    log_x = np.log(x_arr)
                    log_y = np.log(y_arr)
                    poly = np.polyfit(log_x, log_y, 1)
                    beta = float(poly[0])
                    y_pred = np.polyval(poly, log_x)
                    ss_tot = np.sum((log_y - np.mean(log_y)) ** 2)
                    ss_res = np.sum((log_y - y_pred) ** 2)
                    r_sq = float(1.0 - (ss_res / ss_tot)) if ss_tot > 0 else 0.0
                else:
                    poly = np.polyfit(x_arr, y_arr, 1)
                    mean_x = np.mean(x_arr)
                    mean_y = np.mean(y_arr)
                    beta = float(poly[0] * (mean_x / mean_y)) if mean_y != 0 else 0.0
                    y_pred = np.polyval(poly, x_arr)
                    ss_tot = np.sum((y_arr - mean_y) ** 2)
                    ss_res = np.sum((y_arr - y_pred) ** 2)
                    r_sq = float(1.0 - (ss_res / ss_tot)) if ss_tot > 0 else 0.0
            else:
                # Arc elasticity
                y_diff = y_arr[-1] - y_arr[0]
                y_avg = (y_arr[-1] + y_arr[0]) / 2.0
                x_diff = x_arr[-1] - x_arr[0]
                x_avg = (x_arr[-1] + x_arr[0]) / 2.0

                if x_diff != 0 and x_avg != 0 and y_avg != 0:
                    pct_y = y_diff / y_avg
                    pct_x = x_diff / x_avg
                    beta = float(pct_y / pct_x) if pct_x != 0 else 0.0
                else:
                    beta = 0.0
                r_sq = 1.0

            abs_beta = abs(beta)
            if abs_beta > 1.2:
                classification = "Yüksek Esneklik (Elastik)"
            elif abs_beta >= 0.8:
                classification = "Birim Esnekliğe Yakın"
            else:
                classification = "Düşük Esneklik (İnelastik / Katı)"

            direction = "ters (negatif)" if beta < 0 else "doğru (pozitif)"
            interpretation = (
                f"Hesaplanan esneklik katsayısı β = {beta:.3f} olup {classification} kategorisindedir. "
                f"Bağımsız değişkendeki %1'lik bir değişim, bağımlı değişkende yaklaşık %{abs(beta):.2f} oranında "
                f"{direction} yönlü bir değişime yol açmaktadır. R² belirleme katsayısı: {r_sq:.3f}."
            )

            dep_label = dep_id.split(":")[-1]
            indep_label = indep_id.split(":")[-1]
            chart_url = generate_elasticity_chart(
                x_values=paired_x,
                y_values=paired_y,
                x_label=indep_label,
                y_label=dep_label,
                beta=beta,
                r_squared=r_sq,
                title=f"{dep_label} vs {indep_label} Esneklik Analizi",
            )

            return self.Output(
                success=True,
                dependent_series_id=dep_id,
                independent_series_id=indep_id,
                method=params.method,
                elasticity_coefficient=round(beta, 3),
                r_squared=round(max(0.0, r_sq), 3),
                classification=classification,
                interpretation=interpretation,
                chart_url=chart_url,
                sample_size=len(paired_x),
            )

        except Exception as exc:
            logger.exception("elasticity_and_sensitivity_analyzer failed")
            return self.Output(success=False, error=str(exc))
