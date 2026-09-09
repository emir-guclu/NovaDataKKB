"""BDDK FinTürk reconstructed data -> normalized Silver records."""

from __future__ import annotations

import json
import re
from typing import Any

import pandas as pd

from app.modules.bddk.parsers.common import parse_tr_number
from app.modules.bddk.parsers.finturk_reconstruct import reconstruct_finturk


SOURCE = "BDDK_FINTURK"


TABLE_UNITS = {
    1: "bin TL",
    2: "bin TL",
    3: "bin TL",
    4: "bin TL",
    5: "%",
    7: "bin TL",
}


TABLE_6_UNITS = {
    "SubeSayisi": "adet",
    "SubeyeDusenNufus": "kişi",
    "KisiBasiNakdiKredi": "TL",
    "KisiBasiTakiptekiAlacak": "TL",
    "KisiBasiTasarrufMevduati": "TL",
    "KisiBasiToplamMevduat": "TL",
}


def slugify(text: str) -> str:
    """Create stable ASCII snake_case identifiers."""
    text = str(text).strip().lower()

    text = text.translate(
        str.maketrans(
            {
                "ç": "c",
                "ğ": "g",
                "ı": "i",
                "ö": "o",
                "ş": "s",
                "ü": "u",
                "\u0307": "",
            }
        )
    )

    text = re.sub(r"[^a-z0-9]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")

    return text


def resolve_finturk_unit(
    tablo_no: int,
    metric_code: str,
) -> str:
    """Resolve FinTürk unit at table/metric level."""
    tablo_no = int(tablo_no)

    if tablo_no in TABLE_UNITS:
        return TABLE_UNITS[tablo_no]

    if tablo_no == 6:
        unit = TABLE_6_UNITS.get(metric_code)

        if unit is None:
            raise ValueError(
                "Unknown FinTürk table 6 metric unit: "
                f"{metric_code}"
            )

        return unit

    raise ValueError(
        f"Unknown FinTürk table number: {tablo_no}"
    )


def _build_dims(
    sehir: Any,
    grup: Any,
) -> str:
    """Build deterministic geographic FinTürk dimensions."""
    dims: dict[str, str] = {}

    if sehir is not None and not pd.isna(sehir):
        city = str(sehir).strip()

        if city:
            dims["sehir"] = city

    if grup is not None and not pd.isna(grup):
        group_name = str(grup).strip()

        if group_name:
            dims["grup"] = group_name

    return json.dumps(
        dims,
        ensure_ascii=False,
        sort_keys=True,
    )


def _quarter_bounds(
    year: int,
    month: int,
) -> tuple[pd.Timestamp, pd.Timestamp]:
    """
    Convert FinTürk quarter marker month to quarter boundaries.

    FinTürk observations exist at March, June, September, December.
    """
    if month not in {3, 6, 9, 12}:
        raise ValueError(
            "FinTürk period is not quarter-ending: "
            f"{year}-{month:02d}"
        )

    quarter_start_month = month - 2

    period_start = pd.Timestamp(
        year=year,
        month=quarter_start_month,
        day=1,
    )

    period_end = pd.Timestamp(
        year=year,
        month=month,
        day=1,
    ) + pd.offsets.MonthEnd(0)

    return period_start, period_end


def _resolve_value(value_raw: Any) -> float | None:
    """Parse reconstructed FinTürk value."""
    return parse_tr_number(value_raw)


def parse_bddk_finturk(
    df: pd.DataFrame,
    source_file: str | None = None,
    *,
    already_reconstructed: bool = False,
) -> pd.DataFrame:
    """
    Normalize FinTürk Bronze into Silver-ready long-form records.

    Persistent series identity:
        table number + metric code

    Geographic and grouping attributes stay in dims.

    Parameters
    ----------
    df:
        Either flattened FinTürk Bronze data or reconstructed data.
    already_reconstructed:
        Set True when df is output of reconstruct_finturk().
    """
    if already_reconstructed:
        reconstructed = df.copy()
    else:
        reconstructed = reconstruct_finturk(df)

    required = {
        "date",
        "year",
        "month",
        "tablo_no",
        "category",
        "sehir",
        "grup",
        "metric_code",
        "metric_name",
        "value_raw",
    }

    missing = required - set(reconstructed.columns)

    if missing:
        raise ValueError(
            "Missing required reconstructed FinTürk columns: "
            f"{sorted(missing)}"
        )

    records: list[dict[str, Any]] = []

    for _, row in reconstructed.iterrows():
        year = int(row["year"])
        month = int(row["month"])
        tablo_no = int(row["tablo_no"])

        metric_code = str(row["metric_code"]).strip()
        metric_name = str(row["metric_name"]).strip()

        if not metric_code:
            raise ValueError(
                "Encountered empty FinTürk metric_code"
            )

        if not metric_name:
            raise ValueError(
                f"Empty metric_name for {metric_code}"
            )

        period_start, period_end = _quarter_bounds(
            year,
            month,
        )

        unit = resolve_finturk_unit(
            tablo_no,
            metric_code,
        )

        series_id = (
            f"{SOURCE}:"
            f"t{tablo_no}:"
            f"{slugify(metric_code)}"
        )

        records.append(
            {
                "series_id": series_id,
                "source": SOURCE,
                "date": period_end.date(),
                "period_start": period_start.date(),
                "period_end": period_end.date(),
                "value": _resolve_value(
                    row["value_raw"]
                ),
                "freq": "Q",
                "unit": unit,
                "dims": _build_dims(
                    row.get("sehir"),
                    row.get("grup"),
                ),
                "source_file": source_file,
            }
        )

    result = pd.DataFrame.from_records(
        records,
        columns=[
            "series_id",
            "source",
            "date",
            "period_start",
            "period_end",
            "value",
            "freq",
            "unit",
            "dims",
            "source_file",
        ],
    )

    if not result.empty:
        result = result.sort_values(
            [
                "series_id",
                "date",
                "dims",
            ],
            kind="stable",
        ).reset_index(drop=True)

        duplicate_mask = result.duplicated(
            [
                "series_id",
                "date",
                "dims",
            ],
            keep=False,
        )

        if duplicate_mask.any():
            examples = result.loc[
                duplicate_mask,
                [
                    "series_id",
                    "date",
                    "dims",
                    "value",
                ],
            ].head(20)

            raise ValueError(
                "BDDK FinTürk produced duplicate "
                "(series_id, date, dims) observations.\n"
                f"{examples.to_string(index=False)}"
            )

    return result
