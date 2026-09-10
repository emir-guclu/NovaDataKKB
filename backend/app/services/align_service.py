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
from typing import Literal, Mapping

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


def _month_end(value: object) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    last_day = calendar.monthrange(ts.year, ts.month)[1]
    return pd.Timestamp(
        year=ts.year,
        month=ts.month,
        day=last_day,
    )


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
