"""BDDK Monthly Bronze -> normalized Silver-ready records."""

import json
import re
from typing import Any

import pandas as pd

from app.modules.bddk.parsers.common import (
    extract_unit_hint,
    parse_tr_number,
)


SOURCE = "BDDK_MONTHLY"

VERIFIED_UNIT_FALLBACKS = {
    "Diğer Bilgiler": "adet",
    "Rasyolar": "%",
    "Yurt Dışı Şube Rasyoları": "%",
}


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


def monthly_junk_mask(df: pd.DataFrame) -> pd.Series:
    """
    Identify structural/header rows in Monthly Bronze.

    Removes:
    - category/unit header rows containing "Dönem:"
    - Unnamed Excel columns
    - duplicated category-label rows that contain no numeric value
    """
    required = {"variable", "category", "value"}

    missing = required - set(df.columns)

    if missing:
        raise ValueError(
            f"Missing required columns for monthly junk detection: "
            f"{sorted(missing)}"
        )

    variable = df["variable"].astype("string")
    category = df["category"].astype("string")

    classic_junk = variable.str.contains(
        r"Dönem:|Unnamed",
        case=False,
        regex=True,
        na=False,
    )

    category_header_junk = (
        variable.str.strip().eq(category.str.strip())
        & df["value"].isna()
    )

    return classic_junk | category_header_junk


def extract_monthly_unit_map(df: pd.DataFrame) -> dict[str, str]:
    """Extract one verified unit per Monthly BDDK category."""
    required = {"category", "variable"}

    missing = required - set(df.columns)

    if missing:
        raise ValueError(
            f"Missing required columns for monthly unit extraction: "
            f"{sorted(missing)}"
        )

    result: dict[str, str] = {}

    header_rows = df[
        df["variable"]
        .astype("string")
        .str.contains(
            r"Dönem:",
            case=False,
            regex=True,
            na=False,
        )
    ]

    for _, row in header_rows.iterrows():
        category = str(row["category"]).strip()
        hint = extract_unit_hint(row["variable"])

        if hint:
            result[category] = hint

    for category, unit in VERIFIED_UNIT_FALLBACKS.items():
        if category in set(df["category"].dropna().astype(str)):
            result.setdefault(category, unit)

    return result


def _is_child_item(item: Any) -> bool:
    """
    Return True for hierarchical child labels such as:
    a) ...
    b) ...
    c) ...
    """
    if item is None or pd.isna(item):
        return False

    text = str(item).strip()

    return bool(
        re.match(
            r"^[a-zçğıöşü]\)",
            text,
            flags=re.IGNORECASE,
        )
    )


def add_parent_context(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add semantic parent_item using row order within each category/month.

    row_index is used only to reconstruct hierarchy. It is deliberately
    NOT used in series_id because BDDK table row positions can change
    across time.

    Root rows use themselves as parent_item.
    Child rows such as 'a) ...' inherit the most recent root row.
    """
    required = {
        "category",
        "date",
        "row_index",
        "item",
    }

    missing = required - set(df.columns)

    if missing:
        raise ValueError(
            f"Missing required columns for monthly hierarchy: "
            f"{sorted(missing)}"
        )

    work = df.copy()
    work["_original_order"] = range(len(work))

    work = work.sort_values(
        [
            "category",
            "date",
            "row_index",
            "_original_order",
        ],
        kind="stable",
    )

    parent_by_structure: dict[
        tuple[str, str, Any, str],
        str,
    ] = {}

    for (category, date), group in work.groupby(
        ["category", "date"],
        sort=False,
        dropna=False,
    ):
        current_parent: str | None = None

        structural_rows = (
            group[
                ["row_index", "item"]
            ]
            .drop_duplicates()
            .sort_values("row_index", kind="stable")
        )

        for _, structural_row in structural_rows.iterrows():
            item_raw = structural_row["item"]

            if item_raw is None or pd.isna(item_raw):
                raise ValueError(
                    f"Empty monthly item in category={category}, "
                    f"date={date}"
                )

            item = str(item_raw).strip()

            if not item:
                raise ValueError(
                    f"Empty monthly item in category={category}, "
                    f"date={date}"
                )

            if _is_child_item(item):
                if current_parent is None:
                    raise ValueError(
                        f"Child item '{item}' has no parent in "
                        f"category={category}, date={date}"
                    )

                parent = current_parent
            else:
                current_parent = item
                parent = item

            key = (
                str(category),
                str(date),
                structural_row["row_index"],
                item,
            )

            parent_by_structure[key] = parent

    parents: list[str] = []

    for _, row in work.iterrows():
        item = str(row["item"]).strip()

        key = (
            str(row["category"]),
            str(row["date"]),
            row["row_index"],
            item,
        )

        parent = parent_by_structure.get(key)

        if parent is None:
            raise ValueError(
                "Could not resolve Monthly parent context for "
                f"{key}"
            )

        parents.append(parent)

    work["parent_item"] = parents

    work = (
        work.sort_values("_original_order", kind="stable")
        .drop(columns=["_original_order"])
        .reset_index(drop=True)
    )

    return work


def _build_dims(variable: Any) -> str:
    """Store Monthly table column meaning as deterministic JSON."""
    if variable is None or pd.isna(variable):
        return "{}"

    value = str(variable).strip()

    if not value:
        return "{}"

    return json.dumps(
        {"variable": value},
        ensure_ascii=False,
        sort_keys=True,
    )


def _resolve_value(row: pd.Series) -> float | None:
    """Prefer Bronze numeric value and fall back to value_raw."""
    parsed_value = row.get("value")

    if parsed_value is not None and not pd.isna(parsed_value):
        return float(parsed_value)

    return parse_tr_number(row.get("value_raw"))


def parse_bddk_monthly(
    df: pd.DataFrame,
    source_file: str | None = None,
) -> pd.DataFrame:
    """
    Normalize BDDK Monthly Bronze rows into Silver-ready records.

    Series identity:
        category + semantic parent + item

    variable stays in dims.

    row_index is used only to reconstruct hierarchy and never becomes
    part of the persistent series identity.
    """
    required = {
        "date",
        "year",
        "month",
        "category",
        "row_index",
        "item",
        "variable",
        "value_raw",
        "value",
    }

    missing = required - set(df.columns)

    if missing:
        raise ValueError(
            f"Missing required BDDK monthly columns: "
            f"{sorted(missing)}"
        )

    unit_map = extract_monthly_unit_map(df)

    clean = df.loc[~monthly_junk_mask(df)].copy()

    clean["date"] = pd.to_datetime(
        clean["date"],
        errors="raise",
    )

    clean = add_parent_context(clean)

    records: list[dict[str, Any]] = []

    for _, row in clean.iterrows():
        category = str(row["category"]).strip()
        parent_item = str(row["parent_item"]).strip()
        item = str(row["item"]).strip()

        if not category:
            raise ValueError("Encountered empty Monthly category")

        if not parent_item:
            raise ValueError(
                f"Encountered empty parent for item '{item}'"
            )

        if not item:
            raise ValueError(
                f"Encountered empty Monthly item in '{category}'"
            )

        unit = unit_map.get(category)

        if not unit:
            raise ValueError(
                f"Could not resolve BDDK Monthly unit for "
                f"category '{category}'"
            )

        year = int(row["year"])
        month = int(row["month"])

        period_start_ts = pd.Timestamp(
            year=year,
            month=month,
            day=1,
        )

        period_end_ts = (
            period_start_ts + pd.offsets.MonthEnd(0)
        )

        # Avoid repeating root name twice in the identifier.
        if parent_item == item:
            series_id = (
                f"{SOURCE}:"
                f"{slugify(category)}:"
                f"{slugify(item)}"
            )
        else:
            series_id = (
                f"{SOURCE}:"
                f"{slugify(category)}:"
                f"{slugify(parent_item)}:"
                f"{slugify(item)}"
            )

        records.append(
            {
                "series_id": series_id,
                "source": SOURCE,
                "date": period_end_ts.date(),
                "period_start": period_start_ts.date(),
                "period_end": period_end_ts.date(),
                "value": _resolve_value(row),
                "freq": "M",
                "unit": unit,
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
            ].head(10)

            raise ValueError(
                "BDDK Monthly produced duplicate "
                "(series_id, date, dims) observations.\n"
                f"{examples.to_string(index=False)}"
            )

    return result
