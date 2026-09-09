import pandas as pd

from app.modules.bddk.monthly import (
    generate_periods,
    normalize_excel_table,
)


def test_generate_periods_full_range():
    periods = generate_periods()

    assert len(periods) == 66
    assert periods[0]["date"] == "2021-01-01"
    assert periods[-1]["date"] == "2026-06-01"


def test_generate_periods_year_transition():
    periods = generate_periods(
        start_year=2021,
        start_month=11,
        end_year=2022,
        end_month=2,
    )

    assert [
        period["date"]
        for period in periods
    ] == [
        "2021-11-01",
        "2021-12-01",
        "2022-01-01",
        "2022-02-01",
    ]


def test_normalize_excel_table_preserves_precision():
    df = pd.DataFrame(
        {
            "Sıra": [1],
            "Kalem": [
                "TP Mevduat / Katılım Fonları"
            ],
            "On Bin TL'ye Kadar": [
                111878.252
            ],
            "Toplam": [
                9892119.931
            ],
        }
    )

    category = {
        "tablo_no": "9",
        "name": "Mevduat Türler İtibarıyla",
    }

    period = {
        "year": 2024,
        "month": 6,
        "date": "2024-06-01",
    }

    rows = normalize_excel_table(
        df,
        category,
        period,
    )

    precise = next(
        row
        for row in rows
        if row["variable"]
        == "On Bin TL'ye Kadar"
    )

    total = next(
        row
        for row in rows
        if row["variable"] == "Toplam"
    )

    assert precise["value"] == 111878.252
    assert total["value"] == 9892119.931
    assert precise["date"] == "2024-06-01"
    assert precise["tablo_no"] == "9"
