from __future__ import annotations

import logging
import math
from datetime import date, datetime

import pandas as pd
from pathlib import Path
from typing import Any

import duckdb
from pydantic import BaseModel, Field

from backend.app.services.series_data_resolver import canonical_identifier
from backend.app.tools.base import BaseTool

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SILVER_DB = PROJECT_ROOT / "data" / "silver" / "silver.duckdb"
GOLD_DIR = PROJECT_ROOT / "data" / "gold"
GOLD_EVIDENCE = GOLD_DIR / "gold_series_evidence.parquet"
GOLD_PERIODIC = GOLD_DIR / "gold_periodic_change.parquet"


def _format_date(val: Any) -> str | None:
    if val is None:
        return None
    if isinstance(val, (datetime, date)):
        return val.strftime("%Y-%m-%d")
    return str(val).split("T")[0]


def _expected_period_count(
    start_date: str | None,
    end_date: str | None,
    frequency: str | None,
) -> int | None:
    """Return expected observation count between two dates for supported frequencies."""
    if not start_date or not end_date or not frequency:
        return None

    start = pd.Timestamp(start_date)
    end = pd.Timestamp(end_date)
    freq = str(frequency).upper().strip()

    if end < start:
        return None

    aliases = {
        "D": "D",
        "W": "W",
        "M": "ME",
        "Q": "QE",
        "Y": "YE",
        "A": "YE",
    }

    pandas_freq = aliases.get(freq)
    if pandas_freq is None:
        return None

    # Series dates may be period-end dates. Normalize the first expected
    # period to the period containing start, then count through end.
    if freq == "D":
        expected = pd.date_range(start=start, end=end, freq="D")
    elif freq == "W":
        expected = pd.period_range(start=start, end=end, freq="W")
    elif freq == "M":
        expected = pd.period_range(start=start, end=end, freq="M")
    elif freq == "Q":
        expected = pd.period_range(start=start, end=end, freq="Q")
    else:
        expected = pd.period_range(start=start, end=end, freq="Y")

    return len(expected)


def _coverage_missing(
    *,
    observation_count: int,
    null_count: int,
    start_date: str | None,
    end_date: str | None,
    frequency: str | None,
) -> tuple[int, float, int | None]:
    """Combine null observations with calendar gaps without double-counting."""
    expected_count = _expected_period_count(start_date, end_date, frequency)

    if expected_count is None:
        total_slots = observation_count
        missing_count = null_count
    else:
        calendar_gaps = max(expected_count - observation_count, 0)
        total_slots = max(expected_count, observation_count)
        missing_count = calendar_gaps + null_count

    missing_pct = (
        round((missing_count / total_slots) * 100.0, 2)
        if total_slots > 0
        else 0.0
    )

    return missing_count, missing_pct, expected_count


def _calculate_health_score(observation_count: int, missing_pct: float) -> tuple[float, str]:
    """Hesaplar: (health_score [0..100], health_status ['EXCELLENT', 'GOOD', 'FAIR', 'WARNING'])"""
    if observation_count == 0:
        return 0.0, "WARNING"

    score = 100.0 - (missing_pct * 1.5)
    if observation_count < 5:
        score -= 10.0

    score = max(0.0, min(100.0, score))
    score = round(score, 1)

    if score >= 90.0:
        status = "EXCELLENT"
    elif score >= 75.0:
        status = "GOOD"
    elif score >= 50.0:
        status = "FAIR"
    else:
        status = "WARNING"

    return score, status


def _resolve_alignment_policy(
    nature: str | None,
    alignment_override: str | None,
    alignment_method: str | None,
) -> str:
    if alignment_override:
        return alignment_override
    if alignment_method:
        return alignment_method
    if nature == "stock":
        return "last"
    if nature == "flow":
        return "sum"
    if nature in ("rate", "index"):
        return "mean"
    return "last"


class DataHealthReportTool(BaseTool):
    name = "data_health_report"
    description = (
        "Bir zaman serisinin veya Lakehouse tablosunun veri kalitesini, gozlem sayisini, "
        "tarih araligini, eksik veri oranini, kumulatiflik durumunu, hizalama politikasini "
        "ve veri hatti (lineage/provenance) saglik karnesini cikarir. "
        "Veri guvenilirligi, eksik veri kontrolu veya veri kokusu analizlerinde kullan."
    )

    class Input(BaseModel):
        series_id: str | None = Field(
            default=None,
            description="Lakehouse veya Silver zaman serisi ID'si",
        )
        observations: list[dict[str, Any]] | None = Field(
            default=None,
            description="Satir ici gozlem listesi (orn. [{'date': '2024-01-01', 'value': 100}, ...])",
        )
        gold_table: str | None = Field(
            default=None,
            description="Opsiyonel Gold tablosu adi",
        )
        gold_column: str | None = Field(
            default=None,
            description="Opsiyonel Gold kolonu adi",
        )

    class Output(BaseModel):
        success: bool
        error: str | None = None
        series_id: str | None = None
        series_name: str | None = None
        source: str | None = None
        frequency: str | None = None
        unit: str | None = None
        observation_count: int = 0
        expected_observation_count: int | None = None
        start_date: str | None = None
        end_date: str | None = None
        missing_count: int = 0
        missing_pct: float = 0.0
        is_cumulative: bool | None = None
        nature: str | None = None
        alignment_policy: str | None = None
        lineage: dict[str, Any] = Field(default_factory=dict)
        health_score: float = 0.0
        health_status: str = "UNKNOWN"
        summary_sentence: str = ""

    def run(self, params: Input) -> Output:
        try:
            # 1. Satır içi gözlemler kontrolü
            if params.observations:
                return self._evaluate_inline_observations(params.observations, params.series_id)

            # 2. Gold table / column kontrolü
            if params.gold_table and params.gold_column:
                return self._evaluate_gold_column(params.gold_table, params.gold_column)

            # 3. Series ID kontrolü
            if params.series_id:
                # Tablo:kolon formatı kontrolü
                if ":" in params.series_id and not params.series_id.startswith(("EVDS:", "BDDK_", "BIST:")):
                    parts = params.series_id.split(":", 1)
                    if (GOLD_DIR / f"{parts[0]}.parquet").exists():
                        return self._evaluate_gold_column(parts[0], parts[1])

                return self._evaluate_lakehouse_series(params.series_id)

            return self.Output(
                success=False,
                error="En az bir 'series_id', 'observations' veya 'gold_table'+'gold_column' belirtilmelidir.",
            )
        except Exception as exc:
            logger.exception("data_health_report failed")
            return self.Output(success=False, error=str(exc))

    def _evaluate_inline_observations(
        self,
        observations: list[dict[str, Any]],
        series_id: str | None,
    ) -> Output:
        if not observations:
            return self.Output(success=False, error="Gözlem listesi boş olamaz.")

        dates: list[str] = []
        missing_count = 0
        valid_count = 0

        for item in observations:
            d_val = item.get("date") or item.get("period")
            if d_val:
                dates.append(str(d_val).split("T")[0])

            v = item.get("value")
            if v is None:
                missing_count += 1
            elif isinstance(v, float) and math.isnan(v):
                missing_count += 1
            else:
                valid_count += 1

        total_obs = len(observations)
        if total_obs == 0:
            return self.Output(success=False, error="Geçerli gözlem bulunamadı.")

        dates_sorted = sorted(dates) if dates else []
        start_date = dates_sorted[0] if dates_sorted else None
        end_date = dates_sorted[-1] if dates_sorted else None

        missing_pct = round((missing_count / total_obs) * 100.0, 2)
        health_score, health_status = _calculate_health_score(total_obs, missing_pct)

        name = series_id or "Satır İçi Gözlem Serisi"
        summary = (
            f"{name} serisi {start_date or 'N/A'} - {end_date or 'N/A'} aralığında {total_obs} gözlem içermektedir; "
            f"%{missing_pct:.1f} eksik veri oranı ile {health_status} ({health_score:.0f}/100) sağlık skoruna sahiptir."
        )

        return self.Output(
            success=True,
            series_id=series_id or "inline_series",
            series_name=name,
            source="inline",
            observation_count=total_obs,
            start_date=start_date,
            end_date=end_date,
            missing_count=missing_count,
            missing_pct=missing_pct,
            is_cumulative=False,
            nature="unknown",
            alignment_policy="last",
            lineage={"source": "inline_payload", "total_records": total_obs},
            health_score=health_score,
            health_status=health_status,
            summary_sentence=summary,
        )

    def _evaluate_gold_column(self, gold_table: str, gold_column: str) -> Output:
        con = duckdb.connect()
        try:
            lineage_info: dict[str, Any] = {
                "gold_table": gold_table,
                "gold_column": gold_column,
            }

            source_series_id = None
            source_nature = None
            alignment_method = None
            semantic_desc = None

            if GOLD_EVIDENCE.exists():
                evidence_df = con.execute(
                    "SELECT * FROM read_parquet(?) WHERE gold_table = ? AND gold_column = ?",
                    [str(GOLD_EVIDENCE), gold_table, gold_column],
                ).df()

                if not evidence_df.empty:
                    row = evidence_df.iloc[0]
                    source_series_id = row.get("source_series_id")
                    source_nature = row.get("source_nature")
                    alignment_method = row.get("alignment_method")
                    semantic_desc = row.get("semantic_description")

                    lineage_info.update({
                        "source_series_id": source_series_id,
                        "source": row.get("source"),
                        "source_freq": row.get("source_freq"),
                        "source_nature": source_nature,
                        "alignment_method": alignment_method,
                        "dimension_filter": row.get("dimension_filter"),
                        "transformation": row.get("transformation"),
                        "semantic_description": semantic_desc,
                    })

            # Gold tablosunu oku
            parquet_file = GOLD_DIR / f"{gold_table}.parquet"
            if not parquet_file.exists():
                return self.Output(
                    success=False,
                    error=f"Gold tablosu bulunamadı: {gold_table}",
                )

            # Kolon varlığı ve istatistikleri
            con.execute(f"CREATE TEMP VIEW gtable AS SELECT * FROM read_parquet('{parquet_file.as_posix()}')")
            schema_cols = [c[0] for c in con.execute("DESCRIBE gtable").fetchall()]
            if gold_column not in schema_cols:
                return self.Output(
                    success=False,
                    error=f"'{gold_table}' tablosunda '{gold_column}' kolonu bulunamadı.",
                )

            stats = con.execute(
                f"""
                SELECT
                    COUNT(*) as total_count,
                    MIN(date) as min_d,
                    MAX(date) as max_d,
                    COUNT(CASE WHEN "{gold_column}" IS NULL OR isnan("{gold_column}") THEN 1 END) as null_count
                FROM gtable
                """
            ).fetchone()

            total_obs = stats[0] if stats else 0
            start_date = _format_date(stats[1]) if stats else None
            end_date = _format_date(stats[2]) if stats else None
            missing_count = stats[3] if stats else 0
            missing_pct = round((missing_count / total_obs) * 100.0, 2) if total_obs > 0 else 0.0

            # Series metadata kontrolü (eğer source_series_id varsa)
            meta_name = gold_column
            meta_unit = None
            meta_is_cum = False
            meta_freq = None

            if source_series_id and SILVER_DB.exists():
                try:
                    scon = duckdb.connect(str(SILVER_DB), read_only=True)
                    srow = scon.execute(
                        "SELECT series_name, unit, freq, is_cumulative, nature, alignment_override FROM series_metadata WHERE series_id = ?",
                        [source_series_id],
                    ).fetchone()
                    if srow:
                        meta_name = srow[0] or meta_name
                        meta_unit = srow[1]
                        meta_freq = srow[2]
                        meta_is_cum = bool(srow[3])
                        source_nature = srow[4] or source_nature
                        alignment_override = srow[5]
                        if alignment_override:
                            alignment_method = alignment_override
                    scon.close()
                except Exception as exc:
                    logger.debug("Silver metadata lookup error: %s", exc)

            alignment_policy = _resolve_alignment_policy(source_nature, None, alignment_method)
            health_score, health_status = _calculate_health_score(total_obs, missing_pct)

            summary = (
                f"{gold_table}.{gold_column} ({lineage_info.get('source', 'Gold')}) serisi {start_date or 'N/A'} - {end_date or 'N/A'} aralığında "
                f"{total_obs} gözlem içermektedir; %{missing_pct:.1f} eksik veri oranı ile {health_status} ({health_score:.0f}/100) sağlık skoruna sahiptir."
            )

            return self.Output(
                success=True,
                series_id=f"{gold_table}:{gold_column}",
                series_name=meta_name,
                source=lineage_info.get("source", "Gold"),
                frequency=meta_freq or lineage_info.get("source_freq", "M"),
                unit=meta_unit,
                observation_count=total_obs,
                start_date=start_date,
                end_date=end_date,
                missing_count=missing_count,
                missing_pct=missing_pct,
                is_cumulative=meta_is_cum,
                nature=source_nature,
                alignment_policy=alignment_policy,
                lineage=lineage_info,
                health_score=health_score,
                health_status=health_status,
                summary_sentence=summary,
            )
        finally:
            con.close()

    def _evaluate_lakehouse_series(self, series_id: str) -> Output:
        con = duckdb.connect()
        try:
            canonical_req = canonical_identifier(series_id)
            meta_row = None

            # 1. Metadata ara
            if SILVER_DB.exists():
                scon = duckdb.connect(str(SILVER_DB), read_only=True)
                try:
                    all_meta = scon.execute(
                        "SELECT series_id, series_name, source, freq, unit, nature, is_cumulative, alignment_override FROM series_metadata"
                    ).fetchall()
                    for r in all_meta:
                        if r[0] == series_id or canonical_identifier(r[0]) == canonical_req or r[0].endswith(series_id) or series_id.endswith(r[0]):
                            meta_row = r
                            break
                finally:
                    scon.close()

            resolved_id = meta_row[0] if meta_row else series_id

            # 2. Gözlemleri sorgula (silver.duckdb observations veya gold_periodic_change)
            total_obs = 0
            start_date = None
            end_date = None
            missing_count = 0

            found_obs = False

            if SILVER_DB.exists():
                scon = duckdb.connect(str(SILVER_DB), read_only=True)
                try:
                    stats = scon.execute(
                        """
                        SELECT
                            COUNT(*),
                            MIN(date),
                            MAX(date),
                            COUNT(CASE WHEN value IS NULL OR isnan(value) THEN 1 END)
                        FROM observations
                        WHERE series_id = ?
                        """,
                        [resolved_id],
                    ).fetchone()
                    if stats and stats[0] > 0:
                        total_obs = stats[0]
                        start_date = _format_date(stats[1])
                        end_date = _format_date(stats[2])
                        missing_count = stats[3]
                        found_obs = True
                finally:
                    scon.close()

            if not found_obs and GOLD_PERIODIC.exists():
                p_stats = con.execute(
                    """
                    SELECT
                        COUNT(*),
                        MIN(date),
                        MAX(date),
                        COUNT(CASE WHEN value IS NULL OR isnan(value) THEN 1 END)
                    FROM read_parquet(?)
                    WHERE series_id = ?
                    """,
                    [str(GOLD_PERIODIC), resolved_id],
                ).fetchone()
                if p_stats and p_stats[0] > 0:
                    total_obs = p_stats[0]
                    start_date = _format_date(p_stats[1])
                    end_date = _format_date(p_stats[2])
                    missing_count = p_stats[3]
                    found_obs = True

            if not meta_row and not found_obs:
                return self.Output(
                    success=False,
                    error=f"Seri bulunamadi: {series_id}",
                )


            # Metadata değerleri
            s_name = meta_row[1] if meta_row else resolved_id
            s_source = meta_row[2] if meta_row else resolved_id.split(":")[0]
            s_freq = meta_row[3] if meta_row else "M"
            s_unit = meta_row[4] if meta_row else None
            s_nature = meta_row[5] if meta_row else "stock"
            s_is_cum = bool(meta_row[6]) if meta_row else False
            s_align_override = meta_row[7] if meta_row else None

            # Lineage / Evidence ara
            lineage_info: dict[str, Any] = {
                "source_series_id": resolved_id,
                "source": s_source,
                "freq": s_freq,
                "nature": s_nature,
            }
            if GOLD_EVIDENCE.exists():
                ev_df = con.execute(
                    "SELECT * FROM read_parquet(?) WHERE source_series_id = ?",
                    [str(GOLD_EVIDENCE), resolved_id],
                ).df()
                if not ev_df.empty:
                    ev_row = ev_df.iloc[0]
                    lineage_info.update({
                        "gold_table": ev_row.get("gold_table"),
                        "gold_column": ev_row.get("gold_column"),
                        "alignment_method": ev_row.get("alignment_method"),
                        "dimension_filter": ev_row.get("dimension_filter"),
                        "transformation": ev_row.get("transformation"),
                        "semantic_description": ev_row.get("semantic_description"),
                    })

            alignment_policy = _resolve_alignment_policy(
                s_nature,
                s_align_override,
                lineage_info.get("alignment_method"),
            )

            missing_count, missing_pct, expected_obs = _coverage_missing(
                observation_count=total_obs,
                null_count=missing_count,
                start_date=start_date,
                end_date=end_date,
                frequency=s_freq,
            )
            health_score, health_status = _calculate_health_score(total_obs, missing_pct)

            summary = (
                f"{s_name} ({s_source}) serisi {start_date or 'N/A'} - {end_date or 'N/A'} aralığında "
                f"{total_obs} gözlem içermektedir; %{missing_pct:.1f} eksik veri oranı ile {health_status} ({health_score:.0f}/100) sağlık skoruna sahiptir."
            )

            return self.Output(
                success=True,
                series_id=resolved_id,
                series_name=s_name,
                source=s_source,
                frequency=s_freq,
                unit=s_unit,
                observation_count=total_obs,
                expected_observation_count=expected_obs,
                start_date=start_date,
                end_date=end_date,
                missing_count=missing_count,
                missing_pct=missing_pct,
                is_cumulative=s_is_cum,
                nature=s_nature,
                alignment_policy=alignment_policy,
                lineage=lineage_info,
                health_score=health_score,
                health_status=health_status,
                summary_sentence=summary,
            )
        finally:
            con.close()
