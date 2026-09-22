from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import Any, Literal

import duckdb
from pydantic import BaseModel, Field, model_validator

from backend.app.services.inline_series import (
    DIMENSION_IGNORED_WARNING,
    OBSERVATIONS_DESCRIPTION,
    SERIES_ID_DESCRIPTION,
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

SUPPORTED_METRICS = {"value", "mom_abs_change", "mom_pct_change", "yoy_abs_change", "yoy_pct_change"}


def _canonical_identifier(value: str) -> str:
    return canonical_identifier(value)


def _calculate_pearson(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 2:
        return None
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    numerator = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    variance_x = sum((x - mean_x) ** 2 for x in xs)
    variance_y = sum((y - mean_y) ** 2 for y in ys)
    if variance_x <= 0 or variance_y <= 0:
        return None
    denom = math.sqrt(variance_x * variance_y)
    if denom == 0:
        return None
    return numerator / denom


def _resolve_series_and_dimension(
    con: duckdb.DuckDBPyConnection,
    requested_series_id: str,
    requested_dimension: str | None,
) -> tuple[str | None, str | None, str | None, str | None]:
    matched_id, source = resolve_series_location(con, requested_series_id, GOLD_PARQUET, SILVER_DB)
    if not matched_id or not source:
        return None, None, None, f"Seri bulunamadi: {requested_series_id}"

    available_dims = get_available_dimensions(con, matched_id, source, GOLD_PARQUET)
    dimension, dim_err = resolve_dimension(available_dims, requested_dimension)
    if dim_err:
        return matched_id, None, source, dim_err

    return matched_id, dimension, source, None


def _build_source_cte(
    con: duckdb.DuckDBPyConnection,
    series_id: str,
    dimension: str | None,
    source: str,
    alias: str,
    metric: str,
    start_date: str | None,
    end_date: str | None,
) -> tuple[str, list[Any]]:
    where = []
    qparams: list[Any] = []
    if source == "silver":
        view_name = f"view_{alias}"
        create_silver_periodic_view(con, view_name, series_id, dimension)
        cte_sql = f"SELECT CAST(date AS DATE) AS date, {metric} AS value_{alias} FROM {view_name}"
        if start_date and end_date:
            where.append("date BETWEEN ? AND ?")
            qparams.extend([start_date, end_date])
        if where:
            cte_sql += f" WHERE {' AND '.join(where)}"
        return cte_sql, qparams
    else:
        where.append("series_id = ?")
        qparams.append(series_id)
        if dimension is None:
            where.append("json_extract_string(dims, '$.variable') IS NULL")
        else:
            where.append("json_extract_string(dims, '$.variable') = ?")
            qparams.append(dimension)
        if start_date and end_date:
            where.append("CAST(date AS DATE) BETWEEN ? AND ?")
            qparams.extend([start_date, end_date])
        cte_sql = f"""
            SELECT CAST(date AS DATE) AS date, {metric} AS value_{alias}
            FROM read_parquet(?)
            WHERE {' AND '.join(where)}
        """
        return cte_sql, [str(GOLD_PARQUET), *qparams]


CAVEAT_TEXT = (
    "Bu bir korelasyon ölçümüdür, nedensellik ispatı değildir. Ortak bir üçüncü faktör "
    "(enflasyon, küresel finansal koşullar, politika değişikliği) her iki seriyi birlikte etkiliyor olabilir."
)


class CausalityCheckTool(BaseTool):
    name = "causality_check"
    description = (
        "Iki finansal seri arasindaki Pearson korelasyon katsayisini ve gecikmeli korelasyonu "
        "(lead-lag cross-correlation / oncu gosterge tespiti) gercek gold_periodic_change "
        "verisi veya satir ici seriler (observations) uzerinden hesaplar. "
        "max_lag parametresi ile -max_lag...+max_lag donem taranarak iliskinin kac donem/ay "
        "gecikmeyle en guclu seviyeye ulastigi tespit edilir. Bu istatistiksel korelasyondur, "
        "kesin nedensellik ispati degildir; tek seri degisimleri icin KULLANMA, onun icin "
        "change_detection veya anomaly_detection kullan."
    )

    class Input(BaseModel):
        series_id_a: str | None = Field(default=None, description="Birinci Lakehouse series_id")
        observations_a: list[dict] | None = Field(
            default=None,
            description=(
                "Birinci satır içi zaman serisi: [{'date': 'YYYY-MM-DD', 'value': 123.4}, ...]. "
                "Lakehouse dışı veriler için kullanılır. series_id_a ile birlikte KULLANILMAZ."
            ),
        )
        series_id_b: str | None = Field(default=None, description="İkinci Lakehouse series_id")
        observations_b: list[dict] | None = Field(
            default=None,
            description=(
                "İkinci satır içi zaman serisi: [{'date': 'YYYY-MM-DD', 'value': 123.4}, ...]. "
                "Lakehouse dışı veriler için kullanılır. series_id_b ile birlikte KULLANILMAZ."
            ),
        )
        dimension_a: str | None = Field(default=None, description="Birinci seri dimension degeri")
        dimension_b: str | None = Field(default=None, description="Ikinci seri dimension degeri")
        metric: Literal["value", "mom_abs_change", "mom_pct_change", "yoy_abs_change", "yoy_pct_change"] | str = Field(
            default="value",
            description="Korelasyon icin kullanilacak metrik",
        )
        start_date: str | None = Field(default=None, description="Opsiyonel baslangic tarihi, YYYY-MM-DD")
        end_date: str | None = Field(default=None, description="Opsiyonel bitis tarihi, YYYY-MM-DD")
        max_lag: int = Field(
            default=6,
            ge=0,
            le=12,
            description="Gecikmeli korelasyon için taranacak maksimum dönem (ay). -max_lag...+max_lag taranır.",
        )

        @model_validator(mode="after")
        def _validate_sources(self):
            if bool(self.series_id_a) == bool(self.observations_a):
                raise ValueError(
                    "Taraf A için series_id_a veya observations_a parametrelerinden tam olarak biri verilmelidir."
                )
            if bool(self.series_id_b) == bool(self.observations_b):
                raise ValueError(
                    "Taraf B için series_id_b veya observations_b parametrelerinden tam olarak biri verilmelidir."
                )
            return self

    class Output(BaseModel):
        success: bool
        error: str | None = None
        metric: str | None = None
        selected_dimension_a: str | None = None
        selected_dimension_b: str | None = None
        correlation_coefficient: float | None = None
        optimal_lag: int | None = None
        optimal_correlation: float | None = None
        lag_correlations: dict[int, float] = Field(default_factory=dict)
        lead_lag_interpretation: str | None = None
        n_observations: int = 0
        interpretation: str = ""
        caveat: str = Field(
            default=CAVEAT_TEXT,
            description="Zorunlu ekonometrik nedensellik uyarısı",
        )
        data_source_a: str | None = None
        data_source_b: str | None = None
        warnings: list[str] = Field(default_factory=list)

    def run(self, params: Input) -> Output:
        is_inline_a = bool(params.observations_a)
        is_inline_b = bool(params.observations_b)
        data_source_a = "inline" if is_inline_a else "lakehouse"
        data_source_b = "inline" if is_inline_b else "lakehouse"
        warnings: list[str] = []

        if is_inline_a and params.dimension_a:
            warnings.append(f"Taraf A: {DIMENSION_IGNORED_WARNING}")
        if is_inline_b and params.dimension_b:
            warnings.append(f"Taraf B: {DIMENSION_IGNORED_WARNING}")

        if bool(params.start_date) != bool(params.end_date):
            return self.Output(
                success=False,
                error="start_date ve end_date birlikte verilmelidir.",
                metric=params.metric,
                data_source_a=data_source_a,
                data_source_b=data_source_b,
                warnings=warnings,
            )

        con: duckdb.DuckDBPyConnection | None = None
        try:
            if not is_inline_a or not is_inline_b:
                if not GOLD_PARQUET.exists():
                    return self.Output(
                        success=False,
                        error=f"Gold parquet bulunamadi: {GOLD_PARQUET}",
                        metric=params.metric,
                        data_source_a=data_source_a,
                        data_source_b=data_source_b,
                        warnings=warnings,
                    )
                con = duckdb.connect()

            # Taraf A Yükleme
            dimension_a: str | None = None
            if is_inline_a:
                try:
                    rows_a, parse_warn_a = parse_inline_observations(
                        params.observations_a,
                        metric=params.metric,
                        start_date=params.start_date,
                        end_date=params.end_date,
                    )
                    warnings.extend(parse_warn_a)
                except ValueError as exc:
                    return self.Output(
                        success=False,
                        error=f"Taraf A yüklenemedi: {exc}",
                        metric=params.metric,
                        data_source_a=data_source_a,
                        data_source_b=data_source_b,
                        warnings=warnings,
                    )
            else:
                assert con is not None
                series_a, dimension_a, source_a, error = _resolve_series_and_dimension(
                    con, params.series_id_a, params.dimension_a  # type: ignore[arg-type]
                )
                if error:
                    return self.Output(
                        success=False,
                        error=error,
                        metric=params.metric,
                        data_source_a=data_source_a,
                        data_source_b=data_source_b,
                        warnings=warnings,
                    )
                cte_a_sql, params_a = _build_source_cte(
                    con, series_a, dimension_a, source_a, "a", params.metric, params.start_date, params.end_date  # type: ignore[arg-type]
                )
                rows_a_raw = con.execute(f"{cte_a_sql} ORDER BY date", params_a).fetchall()
                rows_a = [(str(r[0]), float(r[1])) for r in rows_a_raw if r[1] is not None]

            # Taraf B Yükleme
            dimension_b: str | None = None
            if is_inline_b:
                try:
                    rows_b, parse_warn_b = parse_inline_observations(
                        params.observations_b,
                        metric=params.metric,
                        start_date=params.start_date,
                        end_date=params.end_date,
                    )
                    warnings.extend(parse_warn_b)
                except ValueError as exc:
                    return self.Output(
                        success=False,
                        error=f"Taraf B yüklenemedi: {exc}",
                        metric=params.metric,
                        selected_dimension_a=dimension_a,
                        data_source_a=data_source_a,
                        data_source_b=data_source_b,
                        warnings=warnings,
                    )
            else:
                assert con is not None
                series_b, dimension_b, source_b, error = _resolve_series_and_dimension(
                    con, params.series_id_b, params.dimension_b  # type: ignore[arg-type]
                )
                if error:
                    return self.Output(
                        success=False,
                        error=error,
                        metric=params.metric,
                        selected_dimension_a=dimension_a,
                        data_source_a=data_source_a,
                        data_source_b=data_source_b,
                        warnings=warnings,
                    )
                cte_b_sql, params_b = _build_source_cte(
                    con, series_b, dimension_b, source_b, "b", params.metric, params.start_date, params.end_date  # type: ignore[arg-type]
                )
                rows_b_raw = con.execute(f"{cte_b_sql} ORDER BY date", params_b).fetchall()
                rows_b = [(str(r[0]), float(r[1])) for r in rows_b_raw if r[1] is not None]

            # Tarih eşleştirme (önce gün bazında, yetersizse ay bazında fallback)
            dict_a = {d: v for d, v in rows_a}
            dict_b = {d: v for d, v in rows_b}
            common_dates = sorted(set(dict_a.keys()) & set(dict_b.keys()))

            if len(common_dates) >= 2:
                xs = [dict_a[d] for d in common_dates]
                ys = [dict_b[d] for d in common_dates]
            else:
                month_a: dict[str, float] = {}
                for d, v in sorted(rows_a, key=lambda x: x[0]):
                    month_a[d[:7]] = v
                month_b: dict[str, float] = {}
                for d, v in sorted(rows_b, key=lambda x: x[0]):
                    month_b[d[:7]] = v
                common_months = sorted(set(month_a.keys()) & set(month_b.keys()))
                if len(common_months) >= 2:
                    xs = [month_a[m] for m in common_months]
                    ys = [month_b[m] for m in common_months]
                    warnings.append(
                        "Gün bazında yeterli ortak tarih bulunamadı; seriler ay bazında (%Y-%m) eşleştirildi."
                    )
                else:
                    return self.Output(
                        success=False,
                        error="Korelasyon icin en az iki ortak gozlem gereklidir.",
                        metric=params.metric,
                        selected_dimension_a=dimension_a,
                        selected_dimension_b=dimension_b,
                        n_observations=len(common_dates),
                        data_source_a=data_source_a,
                        data_source_b=data_source_b,
                        warnings=warnings,
                    )

            n = len(xs)
            mean_x = sum(xs) / n
            mean_y = sum(ys) / n
            numerator = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
            variance_x = sum((x - mean_x) ** 2 for x in xs)
            variance_y = sum((y - mean_y) ** 2 for y in ys)
            if variance_x == 0 or variance_y == 0:
                return self.Output(
                    success=False,
                    error="Korelasyon hesaplanamadi: serilerden en az birinin varyansi sifir.",
                    metric=params.metric,
                    selected_dimension_a=dimension_a,
                    selected_dimension_b=dimension_b,
                    n_observations=n,
                    data_source_a=data_source_a,
                    data_source_b=data_source_b,
                    warnings=warnings,
                )

            corr = numerator / math.sqrt(variance_x * variance_y)

            optimal_lag: int | None = None
            optimal_correlation: float | None = None
            lag_correlations: dict[int, float] = {}
            lead_lag_interpretation: str | None = None

            if params.max_lag > 0 and n >= 4:
                effective_max_lag = min(params.max_lag, n - 4)
                for k in range(-effective_max_lag, effective_max_lag + 1):
                    if k > 0:
                        xs_sub = xs[: n - k]
                        ys_sub = ys[k :]
                    elif k < 0:
                        m = -k
                        xs_sub = xs[m :]
                        ys_sub = ys[: n - m]
                    else:
                        xs_sub = xs
                        ys_sub = ys

                    r_k = _calculate_pearson(xs_sub, ys_sub)
                    if r_k is not None:
                        lag_correlations[k] = round(r_k, 4)

                if lag_correlations:
                    best_k = max(lag_correlations.keys(), key=lambda k: (abs(lag_correlations[k]), -abs(k)))
                    optimal_lag = best_k
                    optimal_correlation = lag_correlations[best_k]

                    name_a = params.series_id_a or "Taraf A"
                    name_b = params.series_id_b or "Taraf B"

                    if optimal_lag > 0:
                        lead_lag_interpretation = (
                            f"En güçlü ilişki, {name_a} {optimal_lag} dönem/ay önden gittiğinde "
                            f"gözleniyor (r = {optimal_correlation:.4f}). Bu, {name_a} serisindeki değişimin "
                            f"{name_b} serisine yaklaşık {optimal_lag} dönem gecikmeyle yansıdığına işaret ediyor."
                        )
                    elif optimal_lag < 0:
                        lead_lag_interpretation = (
                            f"En güçlü ilişki, {name_b} {abs(optimal_lag)} dönem/ay önden gittiğinde "
                            f"gözleniyor (r = {optimal_correlation:.4f}). Bu, {name_b} serisindeki değişimin "
                            f"{name_a} serisine yaklaşık {abs(optimal_lag)} dönem gecikmeyle yansıdığına işaret ediyor."
                        )
                    else:
                        lead_lag_interpretation = (
                            f"En güçlü ilişki eşzamanlı olarak (lag = 0) gözleniyor (r = {optimal_correlation:.4f}). "
                            f"İki seri arasında belirgin bir öncülük/gecikme etkisi tespit edilmedi."
                        )

            return self.Output(
                success=True,
                metric=params.metric,
                selected_dimension_a=dimension_a,
                selected_dimension_b=dimension_b,
                correlation_coefficient=corr,
                optimal_lag=optimal_lag,
                optimal_correlation=optimal_correlation,
                lag_correlations=lag_correlations,
                lead_lag_interpretation=lead_lag_interpretation,
                n_observations=n,
                interpretation=(
                    "Bu sonuc Pearson korelasyon katsayisidir; iliski yonu ve gucunu "
                    "gosterir, tek basina nedensellik ispati degildir."
                ),
                caveat=CAVEAT_TEXT,
                data_source_a=data_source_a,
                data_source_b=data_source_b,
                warnings=warnings,
            )
        except Exception as exc:
            logger.exception("causality_check failed")
            return self.Output(
                success=False,
                error=str(exc),
                metric=params.metric,
                data_source_a=data_source_a,
                data_source_b=data_source_b,
                warnings=warnings,
            )
        finally:
            if con is not None:
                con.close()
