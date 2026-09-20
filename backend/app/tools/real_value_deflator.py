from __future__ import annotations

import logging
import unicodedata
from pathlib import Path
from typing import Any

import duckdb
from pydantic import BaseModel, Field, model_validator

from backend.app.services.chart_generator import generate_deflator_chart
from backend.app.services.inline_series import (
    DIMENSION_IGNORED_WARNING,
    EXACTLY_ONE_SOURCE_ERROR,
    OBSERVATIONS_DESCRIPTION,
    SERIES_ID_DESCRIPTION,
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


class RealValueDeflatorTool(BaseTool):
    name = "real_value_deflator"
    description = (
        "Nominal finansal serileri (kredi, mevduat, ciro, bütçe, altın vb.) TÜFE enflasyonundan "
        "arındırarak reel büyüme oranını, enflasyon erozyonunu (satın alma gücü kaybı) ve alan grafiğini üretir. "
        "Hem Lakehouse serilerini (nominal_series_id) hem de kullanıcı tarafından yüklenen/dış kaynaklı "
        "satır içi serileri (nominal_observations) destekler. Ham nominal değişimleri veya korelasyonu incelemek "
        "için KULLANMA; onlar için change_detection veya causality_check kullanılmalıdır. "
        "Örnek nominal_series_id: 'BDDK_MONTHLY:tuketici_kredileri:tuketici_kredileri_konut', deflator_series_id: 'TP.GENENDEKS.T1' "
        "veya harici veri için nominal_observations."
    )

    class Input(BaseModel):
        nominal_series_id: str | None = Field(
            default=None,
            description="Enflasyondan arındırılacak Lakehouse serisinin ID'si. nominal_observations verilmişse boş bırakılır.",
        )
        nominal_observations: list[dict] | None = Field(
            default=None,
            description="Satır içi gözlemler [{'date': 'YYYY-MM-DD', 'value': 123.4}, ...]. Lakehouse dışı veriler için kullanılır. nominal_series_id ile birlikte KULLANILMAZ.",
        )
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

        @model_validator(mode="after")
        def _validate_sources(self):
            if bool(self.nominal_series_id) == bool(self.nominal_observations):
                raise ValueError(
                    "nominal_series_id veya nominal_observations parametrelerinden tam olarak biri verilmelidir."
                )
            return self

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
        data_source: str = "lakehouse"
        warnings: list[str] = Field(default_factory=list)

    def run(self, params: Input) -> Output:
        is_inline = bool(params.nominal_observations)
        data_source = "inline" if is_inline else "lakehouse"
        warnings: list[str] = []

        if is_inline and params.dimension:
            warnings.append(DIMENSION_IGNORED_WARNING)

        try:
            if not ALIGNED_PARQUET.exists():
                return self.Output(
                    success=False,
                    error=f"Aligned parquet bulunamadi: {ALIGNED_PARQUET}",
                    data_source=data_source,
                    warnings=warnings,
                )

            nom_dict: dict[str, float] = {}
            nom_id: str = "Harici Nominal Seri"

            if is_inline:
                assert params.nominal_observations is not None
                try:
                    parsed_rows, parse_warnings = parse_inline_observations(
                        params.nominal_observations,
                        metric="value",
                        start_date=params.start_date,
                        end_date=params.end_date,
                    )
                    warnings.extend(parse_warnings)
                    nom_dict = dict(parsed_rows)
                except ValueError as exc:
                    return self.Output(
                        success=False,
                        error=f"Nominal satır içi veri yüklenemedi: {exc}",
                        data_source=data_source,
                        warnings=warnings,
                    )
            else:
                con_nom = duckdb.connect()
                try:
                    fetched_dict, fetched_id, _, nom_err = fetch_series_observations(
                        con_nom,
                        params.nominal_series_id,  # type: ignore[arg-type]
                        params.dimension,
                        start_date=params.start_date,
                        end_date=params.end_date,
                        parquet_path=ALIGNED_PARQUET,
                        silver_db_path=SILVER_DB,
                    )
                    if nom_err or not fetched_dict:
                        return self.Output(
                            success=False,
                            error=f"Nominal seri bulunamadi: {params.nominal_series_id}"
                            if not nom_err or "Seri bulunamadi" in nom_err
                            else nom_err,
                            data_source=data_source,
                            warnings=warnings,
                        )
                    nom_dict = fetched_dict
                    nom_id = fetched_id
                finally:
                    con_nom.close()

            con_def = duckdb.connect()
            try:
                def_dict, def_id, _, def_err = fetch_series_observations(
                    con_def,
                    params.deflator_series_id,
                    start_date=params.start_date,
                    end_date=params.end_date,
                    parquet_path=ALIGNED_PARQUET,
                    silver_db_path=SILVER_DB,
                )
                if def_err or not def_dict:
                    return self.Output(
                        success=False,
                        error=f"Deflatör serisi bulunamadi: {params.deflator_series_id}"
                        if not def_err or "Seri bulunamadi" in def_err
                        else def_err,
                        data_source=data_source,
                        warnings=warnings,
                    )
            finally:
                con_def.close()

            # Tarih eşleştirme (önce gün bazında, yetersizse ay bazında fallback)
            common_dates = sorted(set(nom_dict.keys()) & set(def_dict.keys()))
            if len(common_dates) < 2:
                nom_by_month: dict[str, tuple[str, float]] = {
                    d[:7]: (d, v) for d, v in sorted(nom_dict.items())
                }
                def_by_month: dict[str, tuple[str, float]] = {
                    d[:7]: (d, v) for d, v in sorted(def_dict.items())
                }
                common_months = sorted(set(nom_by_month.keys()) & set(def_by_month.keys()))
                if len(common_months) < 2:
                    return self.Output(
                        success=False,
                        error="Analiz için yeterli ortak tarihli veri noktası bulunamadı.",
                        data_source=data_source,
                        warnings=warnings,
                    )

                aligned_dates: list[str] = []
                aligned_nom: dict[str, float] = {}
                aligned_def: dict[str, float] = {}
                for m in common_months:
                    dt_nom, val_nom = nom_by_month[m]
                    _, val_def = def_by_month[m]
                    aligned_dates.append(dt_nom)
                    aligned_nom[dt_nom] = val_nom
                    aligned_def[dt_nom] = val_def

                common_dates = aligned_dates
                nom_dict = aligned_nom
                def_dict = aligned_def
                warnings.append(
                    "Gün bazında yeterli ortak tarih bulunamadı; seriler ay bazında (%Y-%m) eşleştirildi."
                )

            # Baz tarih CPI
            base_date = (
                params.base_date
                if params.base_date and params.base_date in def_dict
                else common_dates[0]
            )
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

            series_name = nom_id.split(":")[-1] if ":" in nom_id else nom_id
            chart_url = generate_deflator_chart(
                dates=dates_list,
                nominal_values=nominal_vals,
                real_values=real_vals,
                series_name=series_name,
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
                data_source=data_source,
                warnings=warnings,
            )

        except Exception as exc:
            logger.exception("real_value_deflator failed")
            return self.Output(success=False, error=str(exc), data_source=data_source, warnings=warnings)
