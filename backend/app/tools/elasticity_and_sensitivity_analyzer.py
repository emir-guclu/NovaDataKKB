from __future__ import annotations

import logging
import unicodedata
from pathlib import Path
from typing import Any, Literal

import duckdb
import numpy as np
from pydantic import BaseModel, Field, model_validator

from backend.app.services.chart_generator import generate_elasticity_chart
from backend.app.services.inline_series import (
    DIMENSION_IGNORED_WARNING,
    OBSERVATIONS_DESCRIPTION,
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


class ElasticityAndSensitivityAnalyzerTool(BaseTool):
    name = "elasticity_and_sensitivity_analyzer"
    description = (
        "İki finansal değişken arasındaki esneklik katsayısını (elasticity) ve duyarlılığı hesaplar "
        "(örn. Faiz veya fiyat değişimlerinin talebe etkisi). OLS log-log regresyon veya "
        "arc elasticity ile saçılım ve trend grafiği üretir. Hem yerel Lakehouse serilerini "
        "(dependent_series_id, independent_series_id) hem de dış kaynaklı satır içi serileri "
        "(observations_dependent, observations_independent) destekler. Doğrudan nedensellik veya anomali tespiti için KULLANMA; "
        "onun için causality_check veya anomaly_detection kullanılmalıdır."
    )

    class Input(BaseModel):
        dependent_series_id: str | None = Field(
            default=None,
            description="Bağımlı değişken serisi ID'si. observations_dependent verilmişse boş bırakılır.",
        )
        observations_dependent: list[dict] | None = Field(
            default=None,
            description=(
                "Bağımlı satır içi zaman serisi: [{'date': 'YYYY-MM-DD', 'value': 123.4}, ...]. "
                "Lakehouse dışı veriler için kullanılır. dependent_series_id ile birlikte KULLANILMAZ."
            ),
        )
        independent_series_id: str | None = Field(
            default=None,
            description="Bağımsız değişken serisi ID'si. observations_independent verilmişse boş bırakılır.",
        )
        observations_independent: list[dict] | None = Field(
            default=None,
            description=(
                "Bağımsız satır içi zaman serisi: [{'date': 'YYYY-MM-DD', 'value': 123.4}, ...]. "
                "Lakehouse dışı veriler için kullanılır. independent_series_id ile birlikte KULLANILMAZ."
            ),
        )
        dependent_dimension: str | None = Field(default=None, description="Bağımlı değişken boyutu (örn: Toplam)")
        independent_dimension: str | None = Field(default=None, description="Bağımsız değişken boyutu")
        lag_months: int = Field(default=0, ge=0, le=24, description="Gecikme süresi (ay cinsinden)")
        method: Literal["arc_elasticity", "log_log_regression"] = Field(
            default="log_log_regression",
            description="Hesaplama metodu ('log_log_regression' veya 'arc_elasticity')",
        )
        start_date: str | None = Field(default=None, description="Başlangıç tarihi (YYYY-MM-DD)")
        end_date: str | None = Field(default=None, description="Bitiş tarihi (YYYY-MM-DD)")

        @model_validator(mode="after")
        def _validate_sources(self):
            if bool(self.dependent_series_id) == bool(self.observations_dependent):
                raise ValueError(
                    "Bağımlı taraf için dependent_series_id veya observations_dependent parametrelerinden tam olarak biri verilmelidir."
                )
            if bool(self.independent_series_id) == bool(self.observations_independent):
                raise ValueError(
                    "Bağımsız taraf için independent_series_id veya observations_independent parametrelerinden tam olarak biri verilmelidir."
                )
            return self

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
        data_source_dependent: str | None = None
        data_source_independent: str | None = None
        warnings: list[str] = Field(default_factory=list)

    def run(self, params: Input) -> Output:
        is_inline_dep = bool(params.observations_dependent)
        is_inline_indep = bool(params.observations_independent)
        data_source_dep = "inline" if is_inline_dep else "lakehouse"
        data_source_indep = "inline" if is_inline_indep else "lakehouse"
        warnings: list[str] = []

        if is_inline_dep and params.dependent_dimension:
            warnings.append(f"Bağımlı taraf: {DIMENSION_IGNORED_WARNING}")
        if is_inline_indep and params.independent_dimension:
            warnings.append(f"Bağımsız taraf: {DIMENSION_IGNORED_WARNING}")

        try:
            # Lakehouse kontrolü: En az bir taraf lakehouse ise ALIGNED_PARQUET aranır
            if not is_inline_dep or not is_inline_indep:
                if not ALIGNED_PARQUET.exists():
                    return self.Output(
                        success=False,
                        error=f"Aligned parquet bulunamadi: {ALIGNED_PARQUET}",
                        data_source_dependent=data_source_dep,
                        data_source_independent=data_source_indep,
                        warnings=warnings,
                    )

            con: duckdb.DuckDBPyConnection | None = None
            if not is_inline_dep or not is_inline_indep:
                con = duckdb.connect()

            dep_data: dict[str, float] = {}
            dep_id: str = params.dependent_series_id or "inline:dependent"

            indep_data: dict[str, float] = {}
            indep_id: str = params.independent_series_id or "inline:independent"

            try:
                # Bağımlı değişken verisi
                if is_inline_dep:
                    try:
                        rows_dep, parse_warn_dep = parse_inline_observations(
                            params.observations_dependent,  # type: ignore
                            metric="value",
                            start_date=params.start_date,
                            end_date=params.end_date,
                        )
                        warnings.extend(parse_warn_dep)
                        dep_data = dict(rows_dep)
                    except ValueError as exc:
                        return self.Output(
                            success=False,
                            error=f"Bağımlı seri yüklenemedi: {exc}",
                            data_source_dependent=data_source_dep,
                            data_source_independent=data_source_indep,
                            warnings=warnings,
                        )
                else:
                    assert con is not None
                    fetched_dep, resolved_dep_id, _, dep_err = fetch_series_observations(
                        con,
                        params.dependent_series_id,  # type: ignore
                        params.dependent_dimension,
                        parquet_path=ALIGNED_PARQUET,
                        silver_db_path=SILVER_DB,
                    )
                    if dep_err or not fetched_dep:
                        return self.Output(
                            success=False,
                            error=f"Bagimli seri bulunamadi: {params.dependent_series_id}"
                            if not dep_err or "Seri bulunamadi" in dep_err
                            else dep_err,
                            data_source_dependent=data_source_dep,
                            data_source_independent=data_source_indep,
                            warnings=warnings,
                        )
                    dep_data = fetched_dep
                    dep_id = resolved_dep_id

                # Bağımsız değişken verisi
                if is_inline_indep:
                    try:
                        rows_indep, parse_warn_indep = parse_inline_observations(
                            params.observations_independent,  # type: ignore
                            metric="value",
                            start_date=params.start_date,
                            end_date=params.end_date,
                        )
                        warnings.extend(parse_warn_indep)
                        indep_data = dict(rows_indep)
                    except ValueError as exc:
                        return self.Output(
                            success=False,
                            error=f"Bağımsız seri yüklenemedi: {exc}",
                            data_source_dependent=data_source_dep,
                            data_source_independent=data_source_indep,
                            warnings=warnings,
                        )
                else:
                    assert con is not None
                    fetched_indep, resolved_indep_id, _, indep_err = fetch_series_observations(
                        con,
                        params.independent_series_id,  # type: ignore
                        params.independent_dimension,
                        parquet_path=ALIGNED_PARQUET,
                        silver_db_path=SILVER_DB,
                    )
                    if indep_err or not fetched_indep:
                        return self.Output(
                            success=False,
                            error=f"Bagimsiz seri bulunamadi: {params.independent_series_id}"
                            if not indep_err or "Seri bulunamadi" in indep_err
                            else indep_err,
                            data_source_dependent=data_source_dep,
                            data_source_independent=data_source_indep,
                            warnings=warnings,
                        )
                    indep_data = fetched_indep
                    indep_id = resolved_indep_id

            finally:
                if con is not None:
                    con.close()

            # Tarihleri sırala ve tarih filtrelerini uygula
            sorted_dates = sorted(set(dep_data.keys()))
            if params.start_date:
                sorted_dates = [d for d in sorted_dates if d >= params.start_date]
            if params.end_date:
                sorted_dates = [d for d in sorted_dates if d <= params.end_date]

            indep_dates = sorted(set(indep_data.keys()))
            if params.start_date:
                indep_dates = [d for d in indep_dates if d >= params.start_date]
            if params.end_date:
                indep_dates = [d for d in indep_dates if d <= params.end_date]

            # Gün bazında eşleşme denemesi (exact date matching with lag)
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
                    paired_x.append(indep_data[lag_dt])
                    paired_y.append(dep_data[dt])

            # Gün bazında eşleşme < 3 ise otomatik %Y-%m ay bazlı fallback eşleştirme
            if len(paired_x) < 3:
                dep_by_month: dict[str, float] = {}
                for d in sorted_dates:
                    dep_by_month[d[:7]] = dep_data[d]

                indep_by_month: dict[str, float] = {}
                for d in indep_dates:
                    indep_by_month[d[:7]] = indep_data[d]

                sorted_indep_months = sorted(indep_by_month.keys())
                month_to_idx = {m: i for i, m in enumerate(sorted_indep_months)}

                fallback_x: list[float] = []
                fallback_y: list[float] = []

                for m in sorted(dep_by_month.keys()):
                    if m not in month_to_idx:
                        continue
                    cur_idx = month_to_idx[m]
                    lag_idx = cur_idx - params.lag_months
                    if 0 <= lag_idx < len(sorted_indep_months):
                        lag_m = sorted_indep_months[lag_idx]
                        fallback_x.append(indep_by_month[lag_m])
                        fallback_y.append(dep_by_month[m])

                if len(fallback_x) >= 3:
                    paired_x = fallback_x
                    paired_y = fallback_y
                    warnings.append(
                        "Gün bazlı doğrudan eşleşme yetersiz kaldığı için seriler ay bazında (%Y-%m) eşleştirildi."
                    )

            if len(paired_x) < 3:
                return self.Output(
                    success=False,
                    error=f"Yeterli gözlem sayısı bulunamadı (mevcut: {len(paired_x)}).",
                    data_source_dependent=data_source_dep,
                    data_source_independent=data_source_indep,
                    warnings=warnings,
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
                data_source_dependent=data_source_dep,
                data_source_independent=data_source_indep,
                warnings=warnings,
            )

        except Exception as exc:
            logger.exception("elasticity_and_sensitivity_analyzer failed")
            return self.Output(
                success=False,
                error=str(exc),
                data_source_dependent=data_source_dep,
                data_source_independent=data_source_indep,
                warnings=warnings,
            )

