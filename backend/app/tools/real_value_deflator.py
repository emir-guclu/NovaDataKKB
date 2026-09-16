from __future__ import annotations

import logging
import unicodedata
from pathlib import Path
from typing import Any

import duckdb
from pydantic import BaseModel, Field

from backend.app.services.chart_generator import generate_deflator_chart
from backend.app.tools.base import BaseTool

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
ALIGNED_PARQUET = PROJECT_ROOT / "data" / "aligned" / "monthly" / "observations.parquet"
SERIES_METADATA_PARQUET = PROJECT_ROOT / "data" / "aligned" / "monthly" / "series_metadata.parquet"


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
                nom_id = _resolve_series_id(con, params.nominal_series_id)
                if not nom_id:
                    return self.Output(success=False, error=f"Nominal seri bulunamadi: {params.nominal_series_id}")

                def_id = _resolve_series_id(con, params.deflator_series_id)
                if not def_id:
                    return self.Output(success=False, error=f"Deflatör serisi bulunamadi: {params.deflator_series_id}")

                # Dimension belirleme
                dim_rows = con.execute(
                    """
                    SELECT DISTINCT json_extract_string(dims, '$.variable') AS dimension
                    FROM read_parquet(?)
                    WHERE series_id = ?
                    """,
                    [str(ALIGNED_PARQUET), nom_id],
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
                query_params: list[Any] = [nom_id]
                if dimension:
                    where_clauses.append("json_extract_string(dims, '$.variable') = ?")
                    query_params.append(dimension)

                if params.start_date:
                    where_clauses.append("date >= ?")
                    query_params.append(params.start_date)
                if params.end_date:
                    where_clauses.append("date <= ?")
                    query_params.append(params.end_date)

                sql_nom = f"""
                    SELECT strftime(date, '%Y-%m-%d') as dt, value
                    FROM read_parquet(?)
                    WHERE {" AND ".join(where_clauses)}
                    ORDER BY date
                """
                nom_rows = con.execute(sql_nom, [str(ALIGNED_PARQUET), *query_params]).fetchall()

                # Deflator verisini çek
                def_where = ["series_id = ?"]
                def_params: list[Any] = [def_id]
                if params.start_date:
                    def_where.append("date >= ?")
                    def_params.append(params.start_date)
                if params.end_date:
                    def_where.append("date <= ?")
                    def_params.append(params.end_date)

                sql_def = f"""
                    SELECT strftime(date, '%Y-%m-%d') as dt, value
                    FROM read_parquet(?)
                    WHERE {" AND ".join(def_where)}
                    ORDER BY date
                """
                def_rows = con.execute(sql_def, [str(ALIGNED_PARQUET), *def_params]).fetchall()

            finally:
                con.close()

            nom_dict = {r[0]: float(r[1]) for r in nom_rows if r[1] is not None}
            def_dict = {r[0]: float(r[1]) for r in def_rows if r[1] is not None}

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
