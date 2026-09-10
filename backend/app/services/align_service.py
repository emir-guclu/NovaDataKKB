"""Cross-source time alignment service for Gold preparation.

Purpose:
- Align D/W/M/Q Silver observations onto a common monthly time axis.
- Avoid blind resampling by requiring explicit aggregation semantics.
- Exclude raw cumulative/YTD series from Gold alignment.
- Preserve quarterly observations sparsely by default to avoid inventing data.
"""

from __future__ import annotations

import calendar
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Literal, Mapping, Optional, Tuple, Union

import duckdb
import pandas as pd


AggregationMethod = Literal["last", "sum", "mean"]
QuarterlyPolicy = Literal["sparse", "ffill"]


@dataclass(frozen=True)
class AlignmentPolicy:
    """Per-series alignment rule."""

    method: AggregationMethod


REQUIRED_OBSERVATION_COLUMNS = {
    "series_id",
    "source",
    "date",
    "value",
    "freq",
    "unit",
    "dims",
}

REQUIRED_METADATA_COLUMNS = {
    "series_id",
    "accumulation",
}


def _week_end(value: object) -> pd.Timestamp:
    """Maps any date to the Friday of its corresponding business week."""
    ts = pd.Timestamp(value)
    weekday = ts.weekday()
    if weekday <= 4:
        delta_days = 4 - weekday
    else:
        delta_days = -(weekday - 4)
    target = ts + pd.Timedelta(days=delta_days)
    return pd.Timestamp(year=target.year, month=target.month, day=target.day)


def _month_end(value: object) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    last_day = calendar.monthrange(ts.year, ts.month)[1]
    return pd.Timestamp(
        year=ts.year,
        month=ts.month,
        day=last_day,
    )


def _quarter_end(value: object) -> pd.Timestamp:
    """Maps any date to the last day of its corresponding calendar quarter."""
    ts = pd.Timestamp(value)
    q_month = ((ts.month - 1) // 3 + 1) * 3
    last_day = calendar.monthrange(ts.year, q_month)[1]
    return pd.Timestamp(year=ts.year, month=q_month, day=last_day)


def _normalize_dims(value: object) -> str:
    if isinstance(value, dict):
        obj = value
    elif value is None or pd.isna(value):
        obj = {}
    else:
        obj = json.loads(str(value))

    if not isinstance(obj, dict):
        raise ValueError("dims must decode to a JSON object")

    return json.dumps(
        obj,
        ensure_ascii=False,
        sort_keys=True,
    )


def _validate_inputs(
    observations: pd.DataFrame,
    metadata: pd.DataFrame,
) -> None:
    missing_obs = (
        REQUIRED_OBSERVATION_COLUMNS
        - set(observations.columns)
    )

    if missing_obs:
        raise ValueError(
            "Missing observation columns: "
            f"{sorted(missing_obs)}"
        )

    missing_meta = (
        REQUIRED_METADATA_COLUMNS
        - set(metadata.columns)
    )

    if missing_meta:
        raise ValueError(
            "Missing metadata columns: "
            f"{sorted(missing_meta)}"
        )

    if metadata["series_id"].duplicated().any():
        raise ValueError(
            "Metadata contains duplicate series_id values"
        )


def _apply_aggregation(
    frame: pd.DataFrame,
    method: AggregationMethod,
) -> float | None:
    values = frame["value"].dropna()

    if values.empty:
        return None

    if method == "last":
        ordered = frame.sort_values("date")
        non_null = ordered[
            ordered["value"].notna()
        ]

        if non_null.empty:
            return None

        return float(
            non_null.iloc[-1]["value"]
        )

    if method == "sum":
        return float(values.sum())

    if method == "mean":
        return float(values.mean())

    raise ValueError(
        f"Unsupported aggregation method: {method!r}"
    )


def _align_daily_or_weekly_group(
    group: pd.DataFrame,
    method: AggregationMethod,
) -> list[dict]:
    rows: list[dict] = []

    work = group.copy()
    work["month_end"] = work["date"].map(
        _month_end
    )

    for month_end, month_group in work.groupby(
        "month_end",
        sort=True,
    ):
        first = month_group.iloc[0]

        rows.append(
            {
                "series_id": first["series_id"],
                "source": first["source"],
                "date": month_end.date(),
                "value": _apply_aggregation(
                    month_group,
                    method,
                ),
                "source_freq": first["freq"],
                "aligned_freq": "M",
                "unit": first["unit"],
                "dims": first["dims"],
                "alignment_method": method,
                "is_imputed": False,
            }
        )

    return rows


def _align_monthly_group(
    group: pd.DataFrame,
) -> list[dict]:
    rows: list[dict] = []

    for _, item in group.sort_values(
        "date"
    ).iterrows():
        rows.append(
            {
                "series_id": item["series_id"],
                "source": item["source"],
                "date": _month_end(
                    item["date"]
                ).date(),
                "value": (
                    None
                    if pd.isna(item["value"])
                    else float(item["value"])
                ),
                "source_freq": "M",
                "aligned_freq": "M",
                "unit": item["unit"],
                "dims": item["dims"],
                "alignment_method": "native",
                "is_imputed": False,
            }
        )

    return rows


def _align_quarterly_sparse(
    group: pd.DataFrame,
) -> list[dict]:
    rows: list[dict] = []

    for _, item in group.sort_values(
        "date"
    ).iterrows():
        rows.append(
            {
                "series_id": item["series_id"],
                "source": item["source"],
                "date": _month_end(
                    item["date"]
                ).date(),
                "value": (
                    None
                    if pd.isna(item["value"])
                    else float(item["value"])
                ),
                "source_freq": "Q",
                "aligned_freq": "M",
                "unit": item["unit"],
                "dims": item["dims"],
                "alignment_method": "quarter_end_sparse",
                "is_imputed": False,
            }
        )

    return rows


def _align_quarterly_ffill(
    group: pd.DataFrame,
) -> list[dict]:
    ordered = group.sort_values(
        "date"
    ).copy()

    ordered["date"] = ordered["date"].map(
        _month_end
    )

    start = ordered["date"].min()
    end = ordered["date"].max()

    monthly_index = pd.date_range(
        start=start,
        end=end,
        freq="ME",
    )

    value_by_month = (
        ordered.set_index("date")["value"]
        .reindex(monthly_index)
        .ffill()
    )

    original_dates = set(
        ordered["date"]
    )

    first = ordered.iloc[0]

    rows: list[dict] = []

    for month_end, value in value_by_month.items():
        if pd.isna(value):
            continue

        rows.append(
            {
                "series_id": first["series_id"],
                "source": first["source"],
                "date": month_end.date(),
                "value": float(value),
                "source_freq": "Q",
                "aligned_freq": "M",
                "unit": first["unit"],
                "dims": first["dims"],
                "alignment_method": "quarter_ffill",
                "is_imputed": (
                    month_end not in original_dates
                ),
            }
        )

    return rows


def align_to_monthly(
    observations: pd.DataFrame,
    metadata: pd.DataFrame,
    policies: Mapping[
        str,
        AlignmentPolicy,
    ],
    *,
    quarterly_policy: QuarterlyPolicy = "sparse",
) -> pd.DataFrame:
    """Align canonical Silver observations to a monthly Gold-ready frame.

    Rules:
    - Raw cumulative series (accumulation != 'none') are excluded.
    - M observations remain monthly.
    - D/W observations require an explicit per-series aggregation policy.
    - Q observations stay sparse by default.
    - Q forward-fill is opt-in only.
    """

    _validate_inputs(
        observations,
        metadata,
    )

    if quarterly_policy not in {
        "sparse",
        "ffill",
    }:
        raise ValueError(
            "quarterly_policy must be 'sparse' or 'ffill'"
        )

    obs = observations.copy()

    obs["date"] = pd.to_datetime(
        obs["date"]
    )

    obs["dims"] = obs["dims"].map(
        _normalize_dims
    )

    accumulation_map = (
        metadata.set_index(
            "series_id"
        )["accumulation"]
        .to_dict()
    )

    obs["accumulation"] = (
        obs["series_id"]
        .map(accumulation_map)
        .fillna("none")
    )

    # Gold must not consume raw YTD / since-start series.
    obs = obs[
        obs["accumulation"] == "none"
    ].copy()

    output_rows: list[dict] = []

    group_columns = [
        "series_id",
        "dims",
    ]

    for (
        series_id,
        _dims,
    ), group in obs.groupby(
        group_columns,
        sort=False,
        dropna=False,
    ):
        freqs = set(
            group["freq"]
            .dropna()
            .astype(str)
        )

        if len(freqs) != 1:
            raise ValueError(
                f"Series {series_id!r} has mixed frequencies: "
                f"{sorted(freqs)}"
            )

        freq = next(iter(freqs))

        if freq in {"D", "W"}:
            policy = policies.get(
                series_id
            )

            if policy is None:
                raise ValueError(
                    "Missing alignment policy for "
                    f"{freq} series {series_id!r}"
                )

            output_rows.extend(
                _align_daily_or_weekly_group(
                    group,
                    policy.method,
                )
            )

        elif freq == "M":
            output_rows.extend(
                _align_monthly_group(
                    group
                )
            )

        elif freq == "Q":
            if quarterly_policy == "sparse":
                output_rows.extend(
                    _align_quarterly_sparse(
                        group
                    )
                )
            else:
                output_rows.extend(
                    _align_quarterly_ffill(
                        group
                    )
                )

        else:
            raise ValueError(
                f"Unsupported source frequency for monthly alignment: {freq!r}"
            )

    result = pd.DataFrame(
        output_rows,
        columns=[
            "series_id",
            "source",
            "date",
            "value",
            "source_freq",
            "aligned_freq",
            "unit",
            "dims",
            "alignment_method",
            "is_imputed",
        ],
    )

    if result.duplicated(
        [
            "series_id",
            "date",
            "dims",
        ]
    ).any():
        raise ValueError(
            "Alignment produced duplicate monthly keys"
        )

    return result.sort_values(
        [
            "series_id",
            "dims",
            "date",
        ]
    ).reset_index(
        drop=True
    )


# =============================================================================
# Dynamic Pair Alignment & Warning Engine (PDF §5.5)
# =============================================================================

DEFAULT_SILVER_DB = (
    Path(__file__).resolve().parents[2].parent
    / "data"
    / "silver"
    / "silver.duckdb"
)

FREQ_RANK = {"D": 1, "W": 2, "M": 3, "Q": 4}


@dataclass
class AlignedPairResult:
    """Encapsulates the synchronized series pair and audit trail warnings."""

    df: pd.DataFrame
    warnings: list[str]
    target_freq: str
    common_periods_count: int
    series_a_id: str
    series_b_id: str
    series_a_method: str
    series_b_method: str
    start_date: Optional[str]
    end_date: Optional[str]

    def __iter__(self):
        """Allows tuple unpacking: df, warnings = align_pair(...)."""
        return iter((self.df, self.warnings))

    def to_dict(self) -> dict[str, Any]:
        """Provides a JSON-serializable dictionary for LLM and API tools."""
        return {
            "target_freq": self.target_freq,
            "common_periods_count": self.common_periods_count,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "series_a_id": self.series_a_id,
            "series_b_id": self.series_b_id,
            "series_a_method": self.series_a_method,
            "series_b_method": self.series_b_method,
            "warnings": self.warnings,
            "data": [
                {
                    "date": str(r["date"]),
                    "value_a": (
                        None
                        if pd.isna(r[self.series_a_id])
                        else float(r[self.series_a_id])
                    ),
                    "value_b": (
                        None
                        if pd.isna(r[self.series_b_id])
                        else float(r[self.series_b_id])
                    ),
                }
                for _, r in self.df.iterrows()
            ],
        }


def generate_alignment_warnings(
    series_a_id: str,
    series_b_id: str,
    freq_a: str,
    freq_b: str,
    target_freq: str,
    method_a: str,
    method_b: str,
    n_common: int,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    quarterly_policy: str = "sparse",
) -> list[str]:
    """Produces human-readable, transparent audit trail warnings according to PDF §5.5."""
    warnings: list[str] = []
    freq_names = {
        "D": "Günlük (D)",
        "W": "Haftalık (W)",
        "M": "Aylık (M)",
        "Q": "Çeyreklik (Q)",
    }
    method_names = {
        "mean": "ortalama (mean)",
        "last": "dönem sonu değeri (last)",
        "sum": "dönem toplamı (sum)",
        "native": "doğal değer (native)",
    }

    # 1. Frequency harmonization notice
    if freq_a != freq_b:
        warnings.append(
            f"⚠️ Frekans uyumsuzluğu: {series_a_id} ({freq_names.get(freq_a, freq_a)}) ve "
            f"{series_b_id} ({freq_names.get(freq_b, freq_b)}) serileri ortak '{freq_names.get(target_freq, target_freq)}' takvimine hizalandı."
        )
    elif freq_a != target_freq:
        warnings.append(
            f"ℹ️ Seriler ({freq_names.get(freq_a, freq_a)}) hedef frekans olan '{freq_names.get(target_freq, target_freq)}' takvimine dönüştürüldü."
        )

    # 2. Aggregation method applied for series A
    if freq_a != target_freq and method_a != "native":
        warnings.append(
            f"ℹ️ {series_a_id} serisi için '{method_names.get(method_a, method_a)}' yöntemi uygulandı."
        )

    # 3. Aggregation method applied for series B
    if freq_b != target_freq and method_b != "native":
        warnings.append(
            f"ℹ️ {series_b_id} serisi için '{method_names.get(method_b, method_b)}' yöntemi uygulandı."
        )

    # 4. Imputation / data fabrication notice
    if "Q" in {freq_a, freq_b} and quarterly_policy == "sparse":
        warnings.append(
            "ℹ️ Veri uydurma (imputation / forward-fill) yapılmadı; çeyreklik veriler yalnızca çeyrek sonlarında bırakıldı."
        )
    else:
        warnings.append(
            "ℹ️ Veri uydurma (imputation) yapılmadı; yalnızca her iki serinin de gerçek gözleminin bulunduğu ortak periyotlar korundu."
        )

    # 5. Coverage notice
    if n_common > 0:
        warnings.append(
            f"ℹ️ Ortak gözlem aralığı: {start_date} ile {end_date} arası ({n_common} periyot)."
        )
    else:
        warnings.append(
            "⚠️ Seriler arasında kesişen ortak bir gözlem aralığı bulunamadı."
        )

    return warnings


def _fetch_series_from_silver_db(
    series_id: str,
    db_path: Path,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Loads a single series and its metadata from silver.duckdb."""
    if not db_path.exists():
        raise FileNotFoundError(f"Silver DuckDB not found at {db_path}")

    con = duckdb.connect(str(db_path), read_only=True)
    try:
        obs_df = con.execute(
            """
            SELECT series_id, source, date, value, freq, unit, dims
            FROM observations
            WHERE series_id = ?
            ORDER BY date ASC
            """,
            [series_id],
        ).fetchdf()

        meta_rows = con.execute(
            """
            SELECT
                series_id,
                source,
                series_code,
                series_name,
                freq,
                unit,
                accumulation,
                nature,
                alignment_override
            FROM series_metadata
            WHERE series_id = ?
            """,
            [series_id],
        ).fetchdf()
    finally:
        con.close()

    if obs_df.empty:
        raise ValueError(f"Series {series_id!r} not found in {db_path.name}")

    meta = meta_rows.iloc[0].to_dict() if not meta_rows.empty else {}
    return obs_df, meta


def _infer_series_aggregation_method(
    series_id: str,
    source: str,
    freq: str,
    nature: str | None,
    alignment_override: str | None = None,
    accumulation: str = "none",
) -> AggregationMethod:
    """Resolve aggregation strictly from canonical financial semantics.

    `source` and `freq` are retained for provenance/API compatibility.
    They are not used as semantic fallbacks.
    """

    del source, freq

    from app.services.series_nature import (
        alignment_method_for_nature,
    )

    if nature is None:
        raise ValueError(
            f"Series {series_id!r} has missing financial nature; "
            "alignment is not allowed."
        )

    nature = str(nature).strip()

    if not nature or nature == "unclassified":
        raise ValueError(
            f"Series {series_id!r} has missing/unclassified "
            "financial nature; alignment is not allowed."
        )

    if alignment_override is not None:
        try:
            if pd.isna(alignment_override):
                alignment_override = None
        except (TypeError, ValueError):
            pass

    if alignment_override is not None:
        alignment_override = str(
            alignment_override
        ).strip() or None

    accumulation = str(accumulation or "none").strip()

    if accumulation != "none":
        return "last"

    return alignment_method_for_nature(
        nature,
        alignment_override,
    )



def _aggregate_series_to_freq(
    df: pd.DataFrame,
    source_freq: str,
    target_freq: str,
    method: AggregationMethod,
    quarterly_policy: QuarterlyPolicy = "sparse",
) -> pd.DataFrame:
    """Downsamples or normalizes a single series DataFrame onto the target frequency."""
    work = df.copy()
    work["date"] = pd.to_datetime(work["date"])

    work = work[work["value"].notna()].copy()
    work["value"] = pd.to_numeric(work["value"], errors="coerce")
    work = work[work["value"].notna()].copy()

    if target_freq == "D":
        work["period_date"] = work["date"].dt.date
    elif target_freq == "W":
        work["period_date"] = work["date"].map(_week_end).dt.date
    elif target_freq == "M":
        work["period_date"] = work["date"].map(_month_end).dt.date
    elif target_freq == "Q":
        work["period_date"] = work["date"].map(_quarter_end).dt.date
    else:
        raise ValueError(f"Unsupported target_freq: {target_freq!r}")

    if source_freq == "Q" and target_freq in {"M", "W", "D"}:
        if quarterly_policy == "sparse":
            grouped_rows = []
            for p_date, grp in work.groupby("period_date", sort=True):
                grouped_rows.append(
                    {
                        "period_date": p_date,
                        "value": _apply_aggregation(grp, method),
                    }
                )
            return pd.DataFrame(grouped_rows)
        elif quarterly_policy == "ffill":
            min_date = work["period_date"].min()
            max_date = work["period_date"].max()
            freq_code = (
                "ME"
                if target_freq == "M"
                else ("W-FRI" if target_freq == "W" else "D")
            )
            idx = pd.date_range(min_date, max_date, freq=freq_code)
            reindexed = (
                work.set_index("period_date")["value"]
                .reindex(idx.date)
                .ffill()
                .reset_index()
            )
            reindexed.columns = ["period_date", "value"]
            return reindexed

    grouped_rows = []
    for p_date, grp in work.groupby("period_date", sort=True):
        agg_val = _apply_aggregation(grp, method)
        grouped_rows.append({"period_date": p_date, "value": agg_val})

    return pd.DataFrame(grouped_rows)


def align_pair(
    series_a: Union[str, pd.DataFrame],
    series_b: Union[str, pd.DataFrame],
    target_freq: Optional[Literal["D", "W", "M", "Q"]] = None,
    method_a: Optional[AggregationMethod] = None,
    method_b: Optional[AggregationMethod] = None,
    quarterly_policy: QuarterlyPolicy = "sparse",
    silver_db_path: Optional[Path] = None,
) -> AlignedPairResult:
    """Dynamically aligns two series onto a synchronized time axis for on-the-fly pair analysis.

    Enables responsive queries such as:
    - Weekly correlation between daily USD/TRY and weekly commercial loans.
    - Monthly panel comparison between policy rate and inflation.
    - Sparse quarterly matching between Finturk NPLs and macro indicators.

    Args:
        series_a: Either a series_id string or a DataFrame containing [date, value, ...].
        series_b: Either a series_id string or a DataFrame containing [date, value, ...].
        target_freq: Target calendar frequency ('D', 'W', 'M', 'Q'). If None, automatically
                     defaults to the coarser frequency of the two series to prevent data fabrication.
        method_a: Aggregation method for series A ('last', 'mean', 'sum'). Auto-resolved if None.
        method_b: Aggregation method for series B ('last', 'mean', 'sum'). Auto-resolved if None.
        quarterly_policy: 'sparse' (default, no imputation) or 'ffill' (opt-in forward fill).
        silver_db_path: Optional path to silver.duckdb (used when series_id strings are provided).

    Returns:
        AlignedPairResult object with .df, .warnings, and .to_dict() methods.
    """
    db_path = silver_db_path or DEFAULT_SILVER_DB

    # 1. Resolve Series A
    if isinstance(series_a, str):
        series_a_id = series_a
        df_a, meta_a = _fetch_series_from_silver_db(series_a, db_path)
        source_a = meta_a.get("source", "UNKNOWN")
        freq_a = meta_a.get("freq") or df_a["freq"].iloc[0]
    else:
        df_a = series_a.copy()
        series_a_id = (
            str(df_a["series_id"].iloc[0])
            if "series_id" in df_a.columns
            else "series_a"
        )
        source_a = (
            str(df_a["source"].iloc[0])
            if "source" in df_a.columns
            else "UNKNOWN"
        )
        freq_a = str(df_a["freq"].iloc[0]) if "freq" in df_a.columns else "M"
        meta_a = {
            "nature": df_a["nature"].iloc[0] if "nature" in df_a.columns else None,
            "alignment_override": df_a["alignment_override"].iloc[0] if "alignment_override" in df_a.columns else None,
            "accumulation": df_a["accumulation"].iloc[0] if "accumulation" in df_a.columns else "none",
        }

    # 2. Resolve Series B
    if isinstance(series_b, str):
        series_b_id = series_b
        df_b, meta_b = _fetch_series_from_silver_db(series_b, db_path)
        source_b = meta_b.get("source", "UNKNOWN")
        freq_b = meta_b.get("freq") or df_b["freq"].iloc[0]
    else:
        df_b = series_b.copy()
        series_b_id = (
            str(df_b["series_id"].iloc[0])
            if "series_id" in df_b.columns
            else "series_b"
        )
        source_b = (
            str(df_b["source"].iloc[0])
            if "source" in df_b.columns
            else "UNKNOWN"
        )
        freq_b = str(df_b["freq"].iloc[0]) if "freq" in df_b.columns else "M"
        meta_b = {
            "nature": df_b["nature"].iloc[0] if "nature" in df_b.columns else None,
            "alignment_override": df_b["alignment_override"].iloc[0] if "alignment_override" in df_b.columns else None,
            "accumulation": df_b["accumulation"].iloc[0] if "accumulation" in df_b.columns else "none",
        }

    # 3. Resolve accumulation semantics

    acc_a = meta_a.get("accumulation", "none") or "none"
    acc_b = meta_b.get("accumulation", "none") or "none"

    # 4. Resolve Target Frequency (Auto-detect if not provided)
    if target_freq is None:
        rank_a = FREQ_RANK.get(freq_a, 3)
        rank_b = FREQ_RANK.get(freq_b, 3)
        target_freq = freq_a if rank_a >= rank_b else freq_b

    # 5. Resolve Aggregation Methods
    res_method_a = method_a or (
        "native"
        if freq_a == target_freq
        else _infer_series_aggregation_method(series_a_id, source_a, freq_a, meta_a.get("nature"), meta_a.get("alignment_override"), acc_a)
    )
    res_method_b = method_b or (
        "native"
        if freq_b == target_freq
        else _infer_series_aggregation_method(series_b_id, source_b, freq_b, meta_b.get("nature"), meta_b.get("alignment_override"), acc_b)
    )

    # 6. Aggregate each series onto target frequency
    agg_df_a = _aggregate_series_to_freq(
        df_a,
        freq_a,
        target_freq,
        "last" if res_method_a == "native" else res_method_a,
        quarterly_policy,
    )
    agg_df_b = _aggregate_series_to_freq(
        df_b,
        freq_b,
        target_freq,
        "last" if res_method_b == "native" else res_method_b,
        quarterly_policy,
    )

    col_a = series_a_id
    col_b = series_b_id if series_b_id != series_a_id else f"{series_b_id}_2"

    agg_df_a = agg_df_a.rename(columns={"value": col_a, "period_date": "date"})
    agg_df_b = agg_df_b.rename(columns={"value": col_b, "period_date": "date"})

    # 7. Inner join on date
    merged_df = (
        pd.merge(agg_df_a, agg_df_b, on="date", how="inner")
        .sort_values("date")
        .reset_index(drop=True)
    )

    n_common = len(merged_df)
    start_date = str(merged_df["date"].min()) if n_common > 0 else None
    end_date = str(merged_df["date"].max()) if n_common > 0 else None

    # 8. Generate Audit Trail Warnings
    warnings = generate_alignment_warnings(
        series_a_id=series_a_id,
        series_b_id=series_b_id,
        freq_a=freq_a,
        freq_b=freq_b,
        target_freq=target_freq,
        method_a=res_method_a,
        method_b=res_method_b,
        n_common=n_common,
        start_date=start_date,
        end_date=end_date,
        quarterly_policy=quarterly_policy,
    )

    return AlignedPairResult(
        df=merged_df,
        warnings=warnings,
        target_freq=target_freq,
        common_periods_count=n_common,
        series_a_id=series_a_id,
        series_b_id=series_b_id,
        series_a_method=res_method_a,
        series_b_method=res_method_b,
        start_date=start_date,
        end_date=end_date,
    )
