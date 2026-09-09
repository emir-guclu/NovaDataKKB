"""Reconstruct BDDK FinTürk jqGrid responses from flattened Bronze rows."""

from __future__ import annotations

import re
from typing import Any

import pandas as pd


_COLNAME_RE = re.compile(r"^Json\.colNames\[(\d+)\]$")
_COLMODEL_NAME_RE = re.compile(
    r"^Json\.colModels\[(\d+)\]\.name$"
)
_CELL_RE = re.compile(
    r"^Json\.data\.rows\[(\d+)\]\.cell\[(\d+)\]$"
)

STRUCTURAL_CODES = {
    "EftKodu",
    "Yil",
    "Ay",
    "Sehir",
    "Grup",
}


def _clean_raw(value: Any) -> Any:
    if value is None:
        return None

    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass

    return value


def _to_int(value: Any, field_name: str) -> int:
    value = _clean_raw(value)

    if value is None:
        raise ValueError(
            f"Missing required FinTürk structural field: {field_name}"
        )

    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"Invalid FinTürk {field_name}: {value!r}"
        ) from exc


def reconstruct_finturk_group(
    group: pd.DataFrame,
) -> pd.DataFrame:
    required = {
        "date",
        "year",
        "month",
        "donem",
        "tablo_no",
        "category",
        "field",
        "value_raw",
    }

    missing = required - set(group.columns)

    if missing:
        raise ValueError(
            "Missing required FinTürk Bronze columns: "
            f"{sorted(missing)}"
        )

    identity = group[
        ["date", "tablo_no", "category"]
    ].drop_duplicates()

    if len(identity) != 1:
        raise ValueError(
            "reconstruct_finturk_group expects exactly one "
            "(date, tablo_no, category) group"
        )

    col_names: dict[int, str] = {}
    col_codes: dict[int, str] = {}
    cells: dict[int, dict[int, Any]] = {}

    for _, row in group.iterrows():
        field = str(row["field"])
        raw = _clean_raw(row["value_raw"])

        m = _COLNAME_RE.match(field)
        if m:
            idx = int(m.group(1))
            if raw is not None:
                col_names[idx] = str(raw).strip()
            continue

        m = _COLMODEL_NAME_RE.match(field)
        if m:
            idx = int(m.group(1))
            if raw is not None:
                col_codes[idx] = str(raw).strip()
            continue

        m = _CELL_RE.match(field)
        if m:
            row_idx = int(m.group(1))
            col_idx = int(m.group(2))
            cells.setdefault(row_idx, {})[col_idx] = raw

    if not cells:
        raise ValueError(
            "No Json.data.rows[N].cell[M] values found "
            "in FinTürk group"
        )

    if not col_codes:
        raise ValueError(
            "No Json.colModels[N].name definitions found "
            "in FinTürk group"
        )

    metadata = identity.iloc[0]

    date = pd.to_datetime(
        metadata["date"],
        errors="raise",
    )

    records: list[dict[str, Any]] = []

    for row_idx in sorted(cells):
        row_cells = cells[row_idx]

        code_to_value: dict[str, Any] = {}

        for col_idx, raw in row_cells.items():
            code = col_codes.get(col_idx)
            if code:
                code_to_value[code] = raw

        eft_kodu = code_to_value.get("EftKodu")
        city = code_to_value.get("Sehir")
        group_name = code_to_value.get("Grup")

        cell_year = code_to_value.get("Yil")
        cell_month = code_to_value.get("Ay")

        year = (
            _to_int(cell_year, "Yil")
            if cell_year is not None
            else int(date.year)
        )

        month = (
            _to_int(cell_month, "Ay")
            if cell_month is not None
            else int(date.month)
        )

        if year != int(date.year) or month != int(date.month):
            raise ValueError(
                "FinTürk inner row period does not match "
                f"Bronze date: inner={year}-{month:02d}, "
                f"outer={date:%Y-%m}"
            )

        if city is None:
            raise ValueError(
                f"FinTürk row {row_idx} has no Sehir value"
            )

        for col_idx in sorted(row_cells):
            metric_code = col_codes.get(col_idx)

            if not metric_code:
                continue

            if metric_code in STRUCTURAL_CODES:
                continue

            metric_name = col_names.get(
                col_idx,
                metric_code,
            )

            records.append(
                {
                    "date": date.date(),
                    "year": year,
                    "month": month,
                    "donem": group["donem"].iloc[0],
                    "tablo_no": int(metadata["tablo_no"]),
                    "category": str(
                        metadata["category"]
                    ).strip(),
                    "row_index": row_idx,
                    "eft_kodu": (
                        None
                        if eft_kodu is None
                        else str(eft_kodu).strip()
                    ),
                    "sehir": str(city).strip(),
                    "grup": (
                        None
                        if group_name is None
                        else str(group_name).strip()
                    ),
                    "metric_index": col_idx,
                    "metric_code": str(
                        metric_code
                    ).strip(),
                    "metric_name": str(
                        metric_name
                    ).strip(),
                    "value_raw": row_cells[col_idx],
                }
            )

    result = pd.DataFrame.from_records(records)

    if result.empty:
        raise ValueError(
            "FinTürk reconstruction produced zero metric rows"
        )

    return result.sort_values(
        [
            "tablo_no",
            "date",
            "row_index",
            "metric_index",
        ],
        kind="stable",
    ).reset_index(drop=True)


def reconstruct_finturk(
    df: pd.DataFrame,
) -> pd.DataFrame:
    required = {
        "date",
        "tablo_no",
        "category",
    }

    missing = required - set(df.columns)

    if missing:
        raise ValueError(
            "Missing required FinTürk grouping columns: "
            f"{sorted(missing)}"
        )

    work = df.copy()

    work["date"] = pd.to_datetime(
        work["date"],
        errors="raise",
    )

    parts: list[pd.DataFrame] = []

    for _, group in work.groupby(
        ["date", "tablo_no", "category"],
        sort=True,
        dropna=False,
    ):
        parts.append(
            reconstruct_finturk_group(group)
        )

    if not parts:
        return pd.DataFrame()

    result = pd.concat(
        parts,
        ignore_index=True,
    )

    duplicate_key = [
        "date",
        "tablo_no",
        "row_index",
        "metric_index",
    ]

    duplicate_mask = result.duplicated(
        duplicate_key,
        keep=False,
    )

    if duplicate_mask.any():
        examples = result.loc[
            duplicate_mask,
            duplicate_key
            + [
                "sehir",
                "metric_code",
                "value_raw",
            ],
        ].head(20)

        raise ValueError(
            "Duplicate reconstructed FinTürk cells detected:\n"
            f"{examples.to_string(index=False)}"
        )

    return result.sort_values(
        [
            "tablo_no",
            "date",
            "row_index",
            "metric_index",
        ],
        kind="stable",
    ).reset_index(drop=True)
