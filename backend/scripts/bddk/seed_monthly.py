import io
import os
import re
import time
import unicodedata
import warnings

import pandas as pd
import requests
import truststore
from bs4 import BeautifulSoup

from app.modules.bddk.common import slugify
from app.modules.bddk.monthly import (
    generate_periods,
    normalize_excel_table,
)


truststore.inject_into_ssl()

warnings.filterwarnings(
    "ignore",
    message="Workbook contains no default style"
)


BASE_URL = "https://www.bddk.org.tr/BultenAylik/"
EXCEL_URL = "https://www.bddk.org.tr/BultenAylik/tr/Home/BasitExceleAktar"

START_YEAR = 2021
START_MONTH = 1

END_YEAR = 2026
END_MONTH = 6

PARA_BIRIMI = "TL"
TARAF = "10001"

REQUEST_DELAY = 0.30
MAX_RETRIES = 3

OUTPUT_DIR = "data/bronze/bddk/monthly"

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
    "Referer": BASE_URL,
})


def request_with_retry(method, url, **kwargs):
    last_error = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = session.request(
                method,
                url,
                timeout=45,
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
                time.sleep(attempt * 2)

    raise last_error


def discover_categories():
    response = request_with_retry(
        "GET",
        BASE_URL
    )

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    categories = []

    for td in soup.find_all("td"):
        td_id = td.get("id", "")

        match = re.match(
            r"tabloListesiItem-(\d+)",
            td_id
        )

        if not match:
            continue

        tablo_no = match.group(1)

        name = td.get_text(
            " ",
            strip=True
        )

        if not name:
            continue

        categories.append({
            "tablo_no": tablo_no,
            "name": name,
            "slug": slugify(name),
        })

    return categories


def read_excel_bytes(content):
    """
    BDDK endpoint'i application/ms-excel dönüyor.
    İçeriği bellekte pandas ile okumayı dener.
    """

    buffer = io.BytesIO(content)

    try:
        df = pd.read_excel(
            buffer,
            engine="openpyxl"
        )

        return df

    except Exception:
        buffer.seek(0)

        df = pd.read_excel(
            buffer
        )

        return df


print()
print("=" * 80)
print("BDDK AYLIK BÜLTEN - TAM HASSASİYETLİ EXCEL TOPLAYICI")
print("=" * 80)


categories = discover_categories()
periods = generate_periods()


print(
    "Kategori sayısı:",
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
    periods[0]["date"]
)

print(
    "Son dönem:",
    periods[-1]["date"]
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


all_rows = []
failures = []


for category_index, category in enumerate(
    categories,
    start=1
):
    print()
    print("=" * 80)

    print(
        f"KATEGORİ "
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
            f"{period['year']}-"
            f"{period['month']:02d}"
        )

        params = [
            (
                "tabloNo",
                category["tablo_no"]
            ),
            (
                "yil",
                str(period["year"])
            ),
            (
                "ay",
                str(period["month"])
            ),
            (
                "paraBirimi",
                PARA_BIRIMI
            ),
            (
                "taraf[0]",
                TARAF
            ),
        ]

        try:
            response = request_with_retry(
                "GET",
                EXCEL_URL,
                params=params
            )

            content_type = (
                response.headers
                .get(
                    "Content-Type",
                    ""
                )
                .lower()
            )

            if (
                "excel" not in content_type
                and len(response.content) < 1000
            ):
                raise RuntimeError(
                    f"Beklenmeyen yanıt: "
                    f"{content_type}"
                )

            df = read_excel_bytes(
                response.content
            )

            rows = normalize_excel_table(
                df,
                category,
                period
            )

            if not rows:
                print(
                    "      UYARI: "
                    "Excel boş veya parse edilemedi."
                )

            category_rows.extend(
                rows
            )

            all_rows.extend(
                rows
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
                "_2021_2026_precise.csv"
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


print()
print("=" * 80)
print("BİRLEŞİK HASSAS AYLIK DATASET OLUŞTURULUYOR")
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
            "row_index",
            "variable",
        ]
    )

    combined_file = os.path.join(
        OUTPUT_DIR,
        "bddk_monthly_all_2021_2026_precise.csv"
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
        "Kategori:",
        all_df[
            "category"
        ].nunique()
    )


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
    "Kategori:",
    len(categories)
)

print(
    "Toplam Excel isteği:",
    len(periods)
    * len(categories)
)

print(
    "Çıktı klasörü:",
    OUTPUT_DIR
)

print("=" * 80)
