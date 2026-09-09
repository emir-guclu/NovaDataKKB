"""BDDK Weekly Bronze -> normalized Silver-ready records."""

import json
import re
from datetime import timedelta
from typing import Any

import pandas as pd

from app.modules.bddk.parsers.common import parse_tr_number


SOURCE = "BDDK_WEEKLY"

# Verified directly against the official BDDK Weekly Bulletin HTML:
# "Tarih: 8 Ocak 2021 Cuma | Birim: Milyon TL"
WEEKLY_UNIT = "milyon TL"


def slugify(text: str) -> str:
    """Create a stable ASCII snake_case identifier."""
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


def _normalize_row_no(value: Any) -> str:
    """Normalize Bronze row_no for deterministic series identifiers."""
    if value is None or pd.isna(value):
        raise ValueError("BDDK weekly row_no cannot be empty")

    if isinstance(value, float) and value.is_integer():
        return str(int(value))

    text = str(value).strip()

    if not text:
        raise ValueError("BDDK weekly row_no cannot be empty")

    if text.endswith(".0"):
        try:
            return str(int(float(text)))
        except ValueError:
            pass

    return text


def _build_dims(variable: Any) -> str:
    """Store TP / YP / TOPLAM as semantic dimension."""
    if variable is None or pd.isna(variable):
        return "{}"

    value = str(variable).strip()

    if not value:
        return "{}"

    return json.dumps(
        {"para_cinsi": value},
        ensure_ascii=False,
        sort_keys=True,
    )


def _resolve_value(row: pd.Series) -> float | None:
    """Prefer Bronze numeric value; fall back to value_raw."""
    parsed = row.get("value")

    if parsed is not None and not pd.isna(parsed):
        return float(parsed)

    return parse_tr_number(row.get("value_raw"))


def parse_bddk_weekly(
    df: pd.DataFrame,
    source_file: str | None = None,
) -> pd.DataFrame:
    """
    Normalize BDDK Weekly Bronze rows.

    Persistent series identity:
        category + row_no + item

    row_no is necessary because the same visible item label can appear
    multiple times in different structural positions in a BDDK table.
    """
    required = {
        "date",
        "category",
        "row_no",
        "item",
        "variable",
        "value_raw",
        "value",
    }

    missing = required - set(df.columns)

    if missing:
        raise ValueError(
            f"Missing required BDDK weekly columns: {sorted(missing)}"
        )

    work = df.copy()
    work["date"] = pd.to_datetime(work["date"], errors="raise")

    records: list[dict[str, Any]] = []

    for _, row in work.iterrows():
        category = str(row["category"]).strip()
        item = str(row["item"]).strip()
        row_no = _normalize_row_no(row["row_no"])

        if not category:
            raise ValueError("Encountered empty BDDK Weekly category")

        if not item:
            raise ValueError(
                f"Encountered empty BDDK Weekly item in '{category}'"
            )

        observation_ts = row["date"]
        observation_date = observation_ts.date()

        period_start = (
            observation_ts
            - timedelta(days=observation_ts.weekday())
        ).date()

        series_id = (
            f"{SOURCE}:"
            f"{slugify(category)}:"
            f"r{slugify(row_no)}:"
            f"{slugify(item)}"
        )

        records.append(
            {
                "series_id": series_id,
                "source": SOURCE,
                "date": observation_date,
                "period_start": period_start,
                "period_end": observation_date,
                "value": _resolve_value(row),
                "freq": "W",
                "unit": WEEKLY_UNIT,
                "dims": _build_dims(row.get("variable")),
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
            ["series_id", "date", "dims"],
            kind="stable",
        ).reset_index(drop=True)

        duplicate_mask = result.duplicated(
            ["series_id", "date", "dims"],
            keep=False,
        )

        if duplicate_mask.any():
            examples = result.loc[
                duplicate_mask,
                ["series_id", "date", "dims", "value"],
            ].head(10)

            raise ValueError(
                "BDDK Weekly produced duplicate "
                "(series_id, date, dims) observations.\n"
                f"{examples.to_string(index=False)}"
            )

    return result
