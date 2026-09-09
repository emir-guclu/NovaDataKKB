import pandas as pd


def generate_periods(
    start_year=2021,
    start_month=1,
    end_year=2026,
    end_month=6,
):
    periods = []

    year = start_year
    month = start_month

    while True:
        periods.append(
            {
                "year": year,
                "month": month,
                "date": f"{year}-{month:02d}-01",
            }
        )

        if year == end_year and month == end_month:
            break

        month += 1

        if month > 12:
            month = 1
            year += 1

    return periods


def normalize_excel_table(
    df,
    category,
    period,
    currency="TL",
):
    rows = []

    if df.empty:
        return rows

    df = df.dropna(axis=1, how="all")
    df = df.dropna(axis=0, how="all")

    df.columns = [
        str(col).strip()
        for col in df.columns
    ]

    for row_index, row in df.iterrows():
        row_values = row.to_dict()

        item = None
        row_no = None
        taraf = None

        for key, value in row_values.items():
            if pd.isna(value):
                continue

            key_lower = key.lower()

            if taraf is None and "banka" in key_lower:
                taraf = str(value)

            if (
                row_no is None
                and (
                    "sıra" in key_lower
                    or "sira" in key_lower
                    or key_lower in {"1", "no"}
                )
            ):
                row_no = value

            if (
                item is None
                and isinstance(value, str)
                and len(value.strip()) > 2
                and value.strip().lower()
                not in {"sektör", "sektor"}
            ):
                item = value.strip()

        for column_name, value in row_values.items():
            if pd.isna(value):
                continue

            if isinstance(value, str):
                candidate = (
                    value.strip()
                    .replace(".", "")
                    .replace(",", ".")
                )

                try:
                    numeric_value = float(candidate)
                except ValueError:
                    numeric_value = None

            elif isinstance(value, (int, float)):
                numeric_value = float(value)

            else:
                numeric_value = None

            rows.append(
                {
                    "date": period["date"],
                    "year": period["year"],
                    "month": period["month"],
                    "tablo_no": category["tablo_no"],
                    "category": category["name"],
                    "row_index": row_index + 1,
                    "row_no": row_no,
                    "item": item,
                    "taraf": taraf,
                    "variable": column_name,
                    "value_raw": value,
                    "value": numeric_value,
                    "currency": currency,
                    "source": "BDDK Aylık Bülten - Excel",
                }
            )

    return rows
