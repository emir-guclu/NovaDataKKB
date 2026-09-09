import re
from datetime import datetime

from .common import parse_tr_number


MONTH_MAP = {
    "ocak": 1,
    "şubat": 2,
    "mart": 3,
    "nisan": 4,
    "mayıs": 5,
    "haziran": 6,
    "temmuz": 7,
    "ağustos": 8,
    "eylül": 9,
    "ekim": 10,
    "kasım": 11,
    "aralık": 12,
}


def find_token(soup) -> str:
    token_input = soup.find(
        "input",
        {"name": "__RequestVerificationToken"},
    )

    if token_input is None:
        raise RuntimeError(
            "__RequestVerificationToken bulunamadı."
        )

    token = token_input.get("value")

    if not token:
        raise RuntimeError("Token değeri boş.")

    return token


def parse_report_date(table):
    first_row = table.find("tr")

    if first_row is None:
        return None

    text = first_row.get_text(" ", strip=True)

    match = re.search(
        r"(\d{1,2})\s+"
        r"(Ocak|Şubat|Mart|Nisan|Mayıs|Haziran|"
        r"Temmuz|Ağustos|Eylül|Ekim|Kasım|Aralık)"
        r"\s+(\d{4})",
        text,
        flags=re.IGNORECASE,
    )

    if not match:
        return None

    day = int(match.group(1))
    month_name = match.group(2).lower()
    year = int(match.group(3))
    month = MONTH_MAP.get(month_name)

    if month is None:
        return None

    return datetime(
        year,
        month,
        day,
    ).strftime("%Y-%m-%d")


def parse_table(soup, category, period):
    table = soup.find(
        "table",
        {"id": "TabloExcel"},
    )

    if table is None:
        raise RuntimeError("TabloExcel bulunamadı.")

    html_rows = table.find_all("tr")

    if not html_rows:
        raise RuntimeError("Tablo boş.")

    report_date = parse_report_date(table)

    header_cells = html_rows[0].find_all(
        ["th", "td"]
    )

    headers = [
        cell.get_text(" ", strip=True)
        for cell in header_cells
    ]

    long_rows = []

    for html_row in html_rows[1:]:
        cells = html_row.find_all(["td", "th"])

        values = [
            cell.get_text(" ", strip=True)
            for cell in cells
        ]

        if not values:
            continue

        row_no = values[0] if len(values) >= 1 else ""
        item = values[1] if len(values) >= 2 else ""

        for col_index in range(2, len(values)):
            raw_value = values[col_index]

            if col_index < len(headers):
                column_name = headers[col_index]
            else:
                column_name = f"column_{col_index}"

            mismatch = (
                report_date is not None
                and report_date != period["dropdown_date"]
            )

            long_rows.append(
                {
                    "date": report_date,
                    "report_date": report_date,
                    "dropdown_date": period["dropdown_date"],
                    "date_mismatch": mismatch,
                    "year": period["year"],
                    "month": period["month"],
                    "day": period["day"],
                    "donem_id": period["donem_id"],
                    "period_text": period["period_text"],
                    "category_id": category["id"],
                    "category": category["name"],
                    "row_no": row_no,
                    "item": item,
                    "variable": column_name,
                    "value_raw": raw_value,
                    "value": parse_tr_number(raw_value),
                    "currency": "TL",
                    "source": "BDDK Haftalık Bülten",
                }
            )

    return long_rows, report_date
