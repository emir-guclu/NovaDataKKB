import os
import re
import time
import unicodedata

import pandas as pd
import requests
import truststore
from bs4 import BeautifulSoup

from app.modules.bddk.common import (
    parse_tr_number,
    slugify,
)
from app.modules.bddk.finturk import flatten_json


truststore.inject_into_ssl()

BASE_URL = "https://www.bddk.org.tr/BultenFinturk/"
REPORT_URL = "https://www.bddk.org.tr/BultenFinturk/tr/Home/VeriGetir"

START_YEAR = 2021
END_YEAR = 2026
END_MONTH = 6

TARAF = "10001"
SEHIR = "HEPSİ"

REQUEST_DELAY = 0.30
MAX_RETRIES = 3

OUTPUT_DIR = "data/bronze/bddk/finturk"

os.makedirs(
    OUTPUT_DIR,
    exist_ok=True
)


session = requests.Session()

session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Version/26.6.2 Safari/605.1.15"
    ),
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": BASE_URL,
})


def request_with_retry(
    method,
    url,
    **kwargs
):
    last_error = None

    for attempt in range(
        1,
        MAX_RETRIES + 1
    ):
        try:
            response = session.request(
                method,
                url,
                timeout=40,
                **kwargs
            )

            response.raise_for_status()

            return response

        except requests.RequestException as exc:
            last_error = exc

            print(
                f"    İstek hatası "
                f"({attempt}/{MAX_RETRIES}): "
                f"{exc}"
            )

            if attempt < MAX_RETRIES:
                time.sleep(
                    attempt * 2
                )

    raise last_error


# ============================================================
# ANA SAYFA VE SEÇENEKLER
# ============================================================

print()
print("=" * 80)
print("BDDK FİNTÜRK - İLLERE GÖRE VERİ TOPLAYICI")
print("=" * 80)


response = request_with_retry(
    "GET",
    BASE_URL
)

soup = BeautifulSoup(
    response.text,
    "html.parser"
)


# Bilgi türleri

table_select = soup.find(
    "select",
    {"id": "ddlTablo"}
)

if table_select is None:
    raise RuntimeError(
        "Bilgi türleri bulunamadı."
    )


categories = []

for option in table_select.find_all(
    "option"
):
    value = option.get("value")
    text = option.get_text(
        " ",
        strip=True
    )

    if not value:
        continue

    categories.append({
        "tablo_no": value,
        "name": text,
        "slug": slugify(text),
    })


# Dönemler

period_select = soup.find(
    "select",
    {"id": "ddlDonem"}
)

if period_select is None:
    raise RuntimeError(
        "Dönem listesi bulunamadı."
    )


periods = []

for option in period_select.find_all(
    "option"
):
    value = option.get("value")

    if not value:
        continue

    match = re.match(
        r"(\d{4})-(\d{1,2})$",
        value
    )

    if not match:
        continue

    year = int(
        match.group(1)
    )

    month = int(
        match.group(2)
    )

    if year < START_YEAR:
        continue

    if year > END_YEAR:
        continue

    if (
        year == END_YEAR
        and month > END_MONTH
    ):
        continue

    periods.append({
        "year": year,
        "month": month,
        "donem": value,
        "date": f"{year}-{month:02d}-01",
    })


periods.sort(
    key=lambda x: (
        x["year"],
        x["month"]
    )
)


print(
    "Bilgi türü:",
    len(categories)
)

for category in categories:
    print(
        f"  {category['tablo_no']} "
        f"→ {category['name']}"
    )


print()
print(
    "Dönem sayısı:",
    len(periods)
)

print(
    "İlk dönem:",
    periods[0]["donem"]
)

print(
    "Son dönem:",
    periods[-1]["donem"]
)


pd.DataFrame(
    categories
).to_csv(
    os.path.join(
        OUTPUT_DIR,
        "categories.csv"
    ),
    index=False,
    encoding="utf-8-sig"
)


pd.DataFrame(
    periods
).to_csv(
    os.path.join(
        OUTPUT_DIR,
        "periods.csv"
    ),
    index=False,
    encoding="utf-8-sig"
)


# ============================================================
# VERİ ÇEKME
# ============================================================

all_rows = []
failures = []


for category_index, category in enumerate(
    categories,
    start=1
):
    print()
    print("=" * 80)

    print(
        f"BİLGİ "
        f"{category_index}/"
        f"{len(categories)}: "
        f"{category['name']}"
    )

    print("=" * 80)

    category_rows = []

    for period_index, period in enumerate(
        periods,
        start=1
    ):
        print(
            f"  "
            f"[{period_index:02d}/"
            f"{len(periods)}] "
            f"{period['donem']}"
        )

        payload = [
            (
                "tabloNo",
                category["tablo_no"]
            ),
            (
                "donem",
                period["donem"]
            ),
            (
                "tarafList[0]",
                TARAF
            ),
            (
                "sehirList[0]",
                SEHIR
            ),
        ]

        try:
            response = request_with_retry(
                "POST",
                REPORT_URL,
                data=payload
            )

            data = response.json()

            flattened = flatten_json(
                data
            )

            if not flattened:
                print(
                    "      UYARI: "
                    "JSON boş döndü."
                )

            for row in flattened:
                record = {
                    "date":
                        period["date"],

                    "year":
                        period["year"],

                    "month":
                        period["month"],

                    "donem":
                        period["donem"],

                    "tablo_no":
                        category[
                            "tablo_no"
                        ],

                    "category":
                        category[
                            "name"
                        ],

                    "field":
                        row[
                            "field"
                        ],

                    "value_raw":
                        row[
                            "value_raw"
                        ],

                    "value":
                        row[
                            "value_numeric"
                        ],

                    "taraf":
                        TARAF,

                    "sehir":
                        SEHIR,

                    "source":
                        "BDDK FinTürk - İllere Göre",
                }

                category_rows.append(
                    record
                )

                all_rows.append(
                    record
                )

        except Exception as exc:
            print(
                "      HATA:",
                exc
            )

            failures.append({
                "year":
                    period["year"],

                "month":
                    period["month"],

                "donem":
                    period["donem"],

                "tablo_no":
                    category[
                        "tablo_no"
                    ],

                "category":
                    category[
                        "name"
                    ],

                "error":
                    str(exc),
            })

        time.sleep(
            REQUEST_DELAY
        )

    category_df = pd.DataFrame(
        category_rows
    )

    if not category_df.empty:
        category_df[
            "date"
        ] = pd.to_datetime(
            category_df["date"]
        )

        category_file = os.path.join(
            OUTPUT_DIR,
            (
                f"{category['slug']}"
                "_2021_2026.csv"
            )
        )

        category_df.to_csv(
            category_file,
            index=False,
            encoding="utf-8-sig"
        )

        print()
        print(
            "Kaydedildi:",
            category_file
        )

        print(
            "Satır:",
            len(category_df)
        )


# ============================================================
# BİRLEŞİK DOSYA
# ============================================================

print()
print("=" * 80)
print(
    "BİRLEŞİK FİNTÜRK DATASET "
    "OLUŞTURULUYOR"
)
print("=" * 80)


all_df = pd.DataFrame(
    all_rows
)

if not all_df.empty:
    all_df[
        "date"
    ] = pd.to_datetime(
        all_df["date"]
    )

    all_df = all_df.sort_values(
        [
            "date",
            "category",
            "field",
        ]
    )

    combined_file = os.path.join(
        OUTPUT_DIR,
        "bddk_finturk_all_2021_2026.csv"
    )

    all_df.to_csv(
        combined_file,
        index=False,
        encoding="utf-8-sig"
    )

    print(
        "Birleşik CSV:",
        combined_file
    )

    print(
        "Toplam satır:",
        len(all_df)
    )

    print(
        "Tarih aralığı:",
        all_df["date"].min(),
        "→",
        all_df["date"].max()
    )

    print(
        "Bilgi türü:",
        all_df["category"].nunique()
    )


# ============================================================
# HATALAR
# ============================================================

if failures:
    failure_df = pd.DataFrame(
        failures
    )

    failure_file = os.path.join(
        OUTPUT_DIR,
        "failures.csv"
    )

    failure_df.to_csv(
        failure_file,
        index=False,
        encoding="utf-8-sig"
    )

    print()
    print(
        "Hatalı istek sayısı:",
        len(failure_df)
    )

    print(
        "Hata dosyası:",
        failure_file
    )

else:
    print()
    print(
        "Hatalı istek yok."
    )


print()
print("=" * 80)
print("TAMAMLANDI")
print("=" * 80)

print(
    "Dönem:",
    len(periods)
)

print(
    "Bilgi türü:",
    len(categories)
)

print(
    "Toplam rapor isteği:",
    len(periods)
    * len(categories)
)

print(
    "Çıktı klasörü:",
    OUTPUT_DIR
)

print("=" * 80)