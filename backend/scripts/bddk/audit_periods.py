import re
import time
from datetime import datetime

import pandas as pd
import requests
import truststore
from bs4 import BeautifulSoup


truststore.inject_into_ssl()

BASE_URL = "https://www.bddk.org.tr/BultenHaftalik/"
PERIOD_POST_URL = "https://www.bddk.org.tr/BultenHaftalik/tr/Home/DonemDegistir"

START_YEAR = 2021
END_YEAR = 2026
END_MONTH = 6

REQUEST_DELAY = 0.25

MONTH_MAP = {
    "Ocak": 1,
    "Şubat": 2,
    "Mart": 3,
    "Nisan": 4,
    "Mayıs": 5,
    "Haziran": 6,
    "Temmuz": 7,
    "Ağustos": 8,
    "Eylül": 9,
    "Ekim": 10,
    "Kasım": 11,
    "Aralık": 12,
}

MONTH_MAP_LOWER = {
    key.lower(): value
    for key, value in MONTH_MAP.items()
}

session = requests.Session()

session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Version/26.6.2 Safari/605.1.15"
    )
})


def get_token(soup):
    token = soup.find(
        "input",
        {"name": "__RequestVerificationToken"}
    )

    if token is None:
        raise RuntimeError("Token bulunamadı.")

    return token["value"]


def parse_report_date(soup):
    table = soup.find(
        "table",
        {"id": "TabloExcel"}
    )

    if table is None:
        return None, None

    first_row = table.find("tr")

    if first_row is None:
        return None, None

    text = first_row.get_text(
        " ",
        strip=True
    )

    match = re.search(
        r"(\d{1,2})\s+"
        r"(Ocak|Şubat|Mart|Nisan|Mayıs|Haziran|"
        r"Temmuz|Ağustos|Eylül|Ekim|Kasım|Aralık)"
        r"\s+(\d{4})",
        text,
        flags=re.IGNORECASE,
    )

    if not match:
        return None, text

    day = int(match.group(1))
    month_name = match.group(2).lower()
    year = int(match.group(3))

    month = MONTH_MAP_LOWER[month_name]

    report_date = datetime(
        year,
        month,
        day
    ).strftime("%Y-%m-%d")

    return report_date, text


# --------------------------------------------------
# 1) Ana sayfa
# --------------------------------------------------

response = session.get(
    BASE_URL,
    timeout=30
)

response.raise_for_status()

soup = BeautifulSoup(
    response.text,
    "html.parser"
)

print("Ana sayfa:", response.status_code)


# --------------------------------------------------
# 2) Dönem listesi
# --------------------------------------------------

select = soup.find(
    "select",
    {"name": "donemId"}
)

if select is None:
    raise RuntimeError("Dönem listesi bulunamadı.")


periods = []

for option in select.find_all("option"):

    donem_id = option.get("value")
    text = option.get_text(" ", strip=True)
    classes = option.get("class", [])

    year = None

    for cls in classes:
        if cls.startswith("Yil-"):
            year = int(cls.replace("Yil-", ""))

    if not donem_id or not year:
        continue

    match = re.search(
        r"([A-Za-zÇĞİÖŞÜçğıöşü]+)/(\d+)",
        text
    )

    if not match:
        continue

    month_name = match.group(1)
    day = int(match.group(2))

    month = MONTH_MAP.get(month_name)

    if month is None:
        continue

    if year < START_YEAR:
        continue

    if year > END_YEAR:
        continue

    if year == END_YEAR and month > END_MONTH:
        continue

    dropdown_date = datetime(
        year,
        month,
        day
    ).strftime("%Y-%m-%d")

    periods.append({
        "donem_id": str(donem_id),
        "dropdown_year": year,
        "dropdown_date": dropdown_date,
        "period_text": text,
    })


print("Kontrol edilecek dönem:", len(periods))


# --------------------------------------------------
# 3) Her dönemi gerçek rapor tarihiyle kontrol et
# --------------------------------------------------

results = []

for index, period in enumerate(
    periods,
    start=1
):

    print(
        f"[{index:03d}/{len(periods)}] "
        f"donemId={period['donem_id']} "
        f"| dropdown={period['dropdown_date']}"
    )

    try:
        # Her istekte güncel token al
        page_response = session.get(
            BASE_URL,
            timeout=30
        )

        page_response.raise_for_status()

        page_soup = BeautifulSoup(
            page_response.text,
            "html.parser"
        )

        token = get_token(page_soup)

        payload = {
            "__RequestVerificationToken": token,
            "yil": str(period["dropdown_year"]),
            "donemId": period["donem_id"],
            "para": "TL",
        }

        report_response = session.post(
            PERIOD_POST_URL,
            data=payload,
            allow_redirects=True,
            timeout=30
        )

        report_response.raise_for_status()

        report_soup = BeautifulSoup(
            report_response.text,
            "html.parser"
        )

        report_date, raw_header = parse_report_date(
            report_soup
        )

        report_year = (
            int(report_date[:4])
            if report_date
            else None
        )

        exact_match = (
            report_date == period["dropdown_date"]
            if report_date
            else False
        )

        year_match = (
            report_year == period["dropdown_year"]
            if report_year
            else False
        )

        if not exact_match:
            print(
                "    FARK → "
                f"rapor={report_date}"
            )

        results.append({
            "donem_id": period["donem_id"],
            "period_text": period["period_text"],
            "dropdown_year": period["dropdown_year"],
            "dropdown_date": period["dropdown_date"],
            "report_year": report_year,
            "report_date": report_date,
            "exact_date_match": exact_match,
            "year_match": year_match,
            "raw_header": raw_header,
            "error": None,
        })

    except Exception as exc:

        print(
            "    HATA:",
            exc
        )

        results.append({
            "donem_id": period["donem_id"],
            "period_text": period["period_text"],
            "dropdown_year": period["dropdown_year"],
            "dropdown_date": period["dropdown_date"],
            "report_year": None,
            "report_date": None,
            "exact_date_match": False,
            "year_match": False,
            "raw_header": None,
            "error": str(exc),
        })

    time.sleep(REQUEST_DELAY)


# --------------------------------------------------
# 4) CSV
# --------------------------------------------------

df = pd.DataFrame(results)

df.to_csv(
    "data/bronze/bddk/audit/period_audit_2021_2026.csv",
    index=False,
    encoding="utf-8-sig"
)


print()
print("=" * 80)

print("AUDIT TAMAMLANDI")

print(
    "Toplam dönem:",
    len(df)
)

print(
    "Tam tarih eşleşen:",
    df["exact_date_match"].sum()
)

print(
    "Tam tarih eşleşmeyen:",
    (~df["exact_date_match"]).sum()
)

print(
    "Yıl eşleşmeyen:",
    (~df["year_match"]).sum()
)

print(
    "Hatalı istek:",
    df["error"].notna().sum()
)

print(
    "Dosya:",
    "data/bronze/bddk/audit/period_audit_2021_2026.csv"
)

print("=" * 80)