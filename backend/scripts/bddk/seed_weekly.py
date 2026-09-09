import os
import re
import time
import unicodedata
from datetime import datetime

import pandas as pd
import requests
import truststore
from bs4 import BeautifulSoup

from app.modules.bddk.common import slugify
from app.modules.bddk.weekly import (
    find_token,
    parse_report_date,
    parse_table,
)


# ============================================================
# SSL
# ============================================================

truststore.inject_into_ssl()


# ============================================================
# AYARLAR
# ============================================================

BASE_URL = "https://www.bddk.org.tr/BultenHaftalik/"
PERIOD_POST_URL = "https://www.bddk.org.tr/BultenHaftalik/tr/Home/DonemDegistir"

START_YEAR = 2021
END_YEAR = 2026
END_MONTH = 6

REQUEST_DELAY = 0.35
MAX_RETRIES = 3

OUTPUT_DIR = "data/bronze/bddk/weekly"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Version/26.6.2 Safari/605.1.15"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,"
        "application/xml;q=0.9,*/*;q=0.8"
    ),
}

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


# ============================================================
# HAZIRLIK
# ============================================================

os.makedirs(
    OUTPUT_DIR,
    exist_ok=True
)

session = requests.Session()
session.headers.update(HEADERS)


# ============================================================
# YARDIMCI FONKSİYONLAR
# ============================================================

def make_soup(response):
    return BeautifulSoup(
        response.text,
        "html.parser"
    )


def find_token(soup):
    token_input = soup.find(
        "input",
        {
            "name":
            "__RequestVerificationToken"
        }
    )

    if token_input is None:
        raise RuntimeError(
            "__RequestVerificationToken bulunamadı."
        )

    token = token_input.get(
        "value"
    )

    if not token:
        raise RuntimeError(
            "Token değeri boş."
        )

    return token


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
# BAŞLANGIÇ
# ============================================================

print()
print("=" * 80)
print(
    "BDDK HAFTALIK BÜLTEN VERİ TOPLAYICI "
    "- TARİH DOĞRULAMALI"
)
print("=" * 80)


# ============================================================
# ANA SAYFA
# ============================================================

response = request_with_retry(
    "GET",
    BASE_URL
)

soup = make_soup(
    response
)

print(
    "Ana sayfa:",
    response.status_code
)


# ============================================================
# DÖNEMLERİ BUL
# ============================================================

donem_select = soup.find(
    "select",
    {"name": "donemId"}
)

if donem_select is None:
    raise RuntimeError(
        "Dönem seçim alanı bulunamadı."
    )


periods = []

for option in donem_select.find_all(
    "option"
):
    donem_id = option.get(
        "value"
    )

    text = option.get_text(
        " ",
        strip=True
    )

    classes = option.get(
        "class",
        []
    )

    year = None

    for cls in classes:
        if cls.startswith(
            "Yil-"
        ):
            try:
                year = int(
                    cls.replace(
                        "Yil-",
                        ""
                    )
                )
            except ValueError:
                pass

    if not donem_id or not year:
        continue

    match = re.search(
        r"([A-Za-zÇĞİÖŞÜçğıöşü]+)/(\d+)",
        text
    )

    if not match:
        continue

    month_name = match.group(
        1
    )

    day = int(
        match.group(2)
    )

    month = MONTH_MAP.get(
        month_name
    )

    if month is None:
        continue

    if year < START_YEAR:
        continue

    if year > END_YEAR:
        continue

    if (
        year == END_YEAR
        and month > END_MONTH
    ):
        continue

    dropdown_date = datetime(
        year,
        month,
        day
    ).strftime(
        "%Y-%m-%d"
    )

    periods.append(
        {
            "year": year,
            "month": month,
            "day": day,
            "dropdown_date": dropdown_date,
            "donem_id": str(
                donem_id
            ),
            "period_text": text,
        }
    )


periods.sort(
    key=lambda x:
    x["dropdown_date"]
)

print(
    "Bulunan dönem:",
    len(periods)
)

print(
    "İlk dropdown tarihi:",
    periods[0]["dropdown_date"]
)

print(
    "Son dropdown tarihi:",
    periods[-1]["dropdown_date"]
)


# ============================================================
# KATEGORİLERİ BUL
# ============================================================

menu = soup.find(
    "table",
    {"id": "manuGrid"}
)

if menu is None:
    raise RuntimeError(
        "Kategori menüsü bulunamadı."
    )


categories = []

for td in menu.find_all(
    "td"
):
    onclick = td.get(
        "onclick",
        ""
    )

    match = re.search(
        r"TabloDegistir\('(\d+)'\)",
        onclick
    )

    if not match:
        continue

    category_id = match.group(
        1
    )

    category_name = td.get_text(
        " ",
        strip=True
    )

    if not category_name:
        continue

    categories.append(
        {
            "id": category_id,
            "name": category_name,
            "slug": slugify(
                category_name
            ),
        }
    )


print()
print(
    "Bulunan kategori:",
    len(categories)
)

for category in categories:
    print(
        f"  {category['id']} "
        f"→ {category['name']}"
    )


# ============================================================
# METADATA KAYDET
# ============================================================

pd.DataFrame(
    periods
).to_csv(
    os.path.join(
        OUTPUT_DIR,
        "periods_dropdown.csv"
    ),
    index=False,
    encoding="utf-8-sig"
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


# ============================================================
# TABLO PARSER
# ============================================================

# ============================================================
# VERİ TOPLAMA
# ============================================================

all_data = []
failures = []
mismatches = []

total_categories = len(
    categories
)

total_periods = len(
    periods
)


for category_index, category in enumerate(
    categories,
    start=1
):
    print()
    print("=" * 80)

    print(
        f"KATEGORİ "
        f"{category_index}/"
        f"{total_categories}: "
        f"{category['name']}"
    )

    print("=" * 80)

    # --------------------------------------------------------
    # KATEGORİ SEÇ
    # --------------------------------------------------------

    current_response = request_with_retry(
        "GET",
        BASE_URL
    )

    current_soup = make_soup(
        current_response
    )

    token = find_token(
        current_soup
    )

    category_payload = {
        "__RequestVerificationToken":
            token,
        "tabloId":
            category["id"],
    }

    category_response = request_with_retry(
        "POST",
        BASE_URL,
        data=category_payload,
        allow_redirects=True
    )

    print(
        "Kategori seçildi:",
        category["name"]
    )

    category_rows = []

    # --------------------------------------------------------
    # TÜM DÖNEMLER
    # --------------------------------------------------------

    for period_index, period in enumerate(
        periods,
        start=1
    ):
        print(
            f"  "
            f"[{period_index:03d}/"
            f"{total_periods}] "
            f"dropdown="
            f"{period['dropdown_date']} "
            f"| donemId="
            f"{period['donem_id']}"
        )

        try:
            current_soup = make_soup(
                category_response
            )

            token = find_token(
                current_soup
            )

            period_payload = {
                "__RequestVerificationToken":
                    token,

                "yil":
                    str(
                        period["year"]
                    ),

                "donemId":
                    period[
                        "donem_id"
                    ],

                "para":
                    "TL",
            }

            period_response = request_with_retry(
                "POST",
                PERIOD_POST_URL,
                data=period_payload,
                allow_redirects=True
            )

            period_soup = make_soup(
                period_response
            )

            rows, report_date = parse_table(
                period_soup,
                category,
                period
            )

            if report_date is None:
                print(
                    "      UYARI: "
                    "rapor tarihi parse edilemedi"
                )

            elif (
                report_date
                != period["dropdown_date"]
            ):
                print(
                    "      TARİH FARKI: "
                    f"dropdown="
                    f"{period['dropdown_date']} "
                    f"rapor="
                    f"{report_date}"
                )

                mismatches.append(
                    {
                        "category":
                            category["name"],

                        "category_id":
                            category["id"],

                        "donem_id":
                            period[
                                "donem_id"
                            ],

                        "period_text":
                            period[
                                "period_text"
                            ],

                        "dropdown_date":
                            period[
                                "dropdown_date"
                            ],

                        "report_date":
                            report_date,
                    }
                )

            category_rows.extend(
                rows
            )

            all_data.extend(
                rows
            )

            category_response = (
                period_response
            )

        except Exception as exc:
            print(
                "      HATA:",
                exc
            )

            failures.append(
                {
                    "category":
                        category["name"],

                    "category_id":
                        category["id"],

                    "dropdown_date":
                        period[
                            "dropdown_date"
                        ],

                    "donem_id":
                        period[
                            "donem_id"
                        ],

                    "error":
                        str(exc),
                }
            )

            # Recovery
            try:
                recovery = request_with_retry(
                    "GET",
                    BASE_URL
                )

                recovery_soup = make_soup(
                    recovery
                )

                recovery_token = find_token(
                    recovery_soup
                )

                recovery_payload = {
                    "__RequestVerificationToken":
                        recovery_token,

                    "tabloId":
                        category["id"],
                }

                category_response = request_with_retry(
                    "POST",
                    BASE_URL,
                    data=recovery_payload,
                    allow_redirects=True
                )

            except Exception as recovery_error:
                print(
                    "      Recovery hatası:",
                    recovery_error
                )

        time.sleep(
            REQUEST_DELAY
        )

    # ========================================================
    # KATEGORİ CSV
    # ========================================================

    category_df = pd.DataFrame(
        category_rows
    )

    if not category_df.empty:
        category_df[
            "date"
        ] = pd.to_datetime(
            category_df["date"],
            errors="coerce"
        )

        category_df[
            "report_date"
        ] = pd.to_datetime(
            category_df[
                "report_date"
            ],
            errors="coerce"
        )

        category_df[
            "dropdown_date"
        ] = pd.to_datetime(
            category_df[
                "dropdown_date"
            ],
            errors="coerce"
        )

        category_df = (
            category_df.sort_values(
                [
                    "date",
                    "row_no",
                    "variable",
                ]
            )
        )

        category_file = os.path.join(
            OUTPUT_DIR,
            (
                f"{category['slug']}"
                "_2021_2026_verified.csv"
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
# BİRLEŞİK DATASET
# ============================================================

print()
print("=" * 80)
print(
    "BİRLEŞİK DATASET OLUŞTURULUYOR"
)
print("=" * 80)


all_df = pd.DataFrame(
    all_data
)

if not all_df.empty:
    all_df["date"] = pd.to_datetime(
        all_df["date"],
        errors="coerce"
    )

    all_df[
        "report_date"
    ] = pd.to_datetime(
        all_df["report_date"],
        errors="coerce"
    )

    all_df[
        "dropdown_date"
    ] = pd.to_datetime(
        all_df["dropdown_date"],
        errors="coerce"
    )

    all_df = all_df.sort_values(
        [
            "date",
            "category",
            "row_no",
            "variable",
        ]
    )

    combined_csv = os.path.join(
        OUTPUT_DIR,
        (
            "bddk_weekly_all_"
            "2021_2026_verified.csv"
        )
    )

    all_df.to_csv(
        combined_csv,
        index=False,
        encoding="utf-8-sig"
    )

    print(
        "Birleşik CSV:",
        combined_csv
    )

    print(
        "Toplam veri satırı:",
        len(all_df)
    )

    print(
        "Rapor tarih aralığı:",
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


# ============================================================
# TARİH UYUŞMAZLIKLARI
# ============================================================

if mismatches:
    mismatch_df = pd.DataFrame(
        mismatches
    )

    mismatch_df = (
        mismatch_df
        .drop_duplicates()
        .sort_values(
            [
                "report_date",
                "category"
            ]
        )
    )

    mismatch_file = os.path.join(
        OUTPUT_DIR,
        "date_mismatches.csv"
    )

    mismatch_df.to_csv(
        mismatch_file,
        index=False,
        encoding="utf-8-sig"
    )

    print()
    print(
        "Tarih uyuşmazlığı sayısı:",
        len(mismatch_df)
    )

    print(
        "Dosya:",
        mismatch_file
    )

else:
    print()
    print(
        "Dropdown ve gerçek rapor "
        "tarihleri arasında "
        "uyuşmazlık bulunmadı."
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
        len(failures)
    )

    print(
        "Hata listesi:",
        failure_file
    )

else:
    print()
    print(
        "Hatalı dönem yok."
    )


# ============================================================
# SONUÇ
# ============================================================

print()
print("=" * 80)
print("TAMAMLANDI")
print("=" * 80)

print(
    "Dönem sayısı:",
    len(periods)
)

print(
    "Kategori sayısı:",
    len(categories)
)

print(
    "Çıktı klasörü:",
    OUTPUT_DIR
)

print("=" * 80)