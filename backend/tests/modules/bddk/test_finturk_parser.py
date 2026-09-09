import json

import pandas as pd
import pytest

from app.modules.bddk.parsers.bddk_finturk import (
    parse_bddk_finturk,
    resolve_finturk_unit,
)
from app.modules.bddk.parsers.finturk_reconstruct import (
    reconstruct_finturk_group,
)


def _flattened_table1_sample():
    common = {
        "date": "2021-03-01",
        "year": 2021,
        "month": 3,
        "donem": "2021-3",
        "tablo_no": 1,
        "category": "Krediler (Bin TL)",
        "taraf": "10001",
        "sehir": "HEPSİ",
        "source": "BDDK_FINTURK",
    }

    fields = [
        ("Json.colModels[0].name", "EftKodu"),
        ("Json.colModels[1].name", "Yil"),
        ("Json.colModels[2].name", "Ay"),
        ("Json.colModels[3].name", "Sehir"),
        ("Json.colModels[4].name", "Grup"),
        ("Json.colModels[5].name", "ToplamNakdiKrediler"),

        ("Json.colNames[0]", "Eftodu"),
        ("Json.colNames[1]", "Yıl"),
        ("Json.colNames[2]", "Ay"),
        ("Json.colNames[3]", "Şehir"),
        ("Json.colNames[4]", "Grup"),
        ("Json.colNames[5]", "Toplam Nakdi Krediler"),

        ("Json.data.rows[0].cell[0]", "10001"),
        ("Json.data.rows[0].cell[1]", "2021"),
        ("Json.data.rows[0].cell[2]", "3"),
        ("Json.data.rows[0].cell[3]", "ADANA"),
        ("Json.data.rows[0].cell[4]", "SEKTÖR"),
        ("Json.data.rows[0].cell[5]", "65046605"),
    ]

    rows = []

    for field, value_raw in fields:
        row = dict(common)
        row["field"] = field
        row["value_raw"] = value_raw
        row["value"] = None
        rows.append(row)

    return pd.DataFrame(rows)


def test_reconstruct_finturk_uses_inner_city_not_query_city():
    raw = _flattened_table1_sample()

    result = reconstruct_finturk_group(raw)

    assert len(result) == 1

    row = result.iloc[0]

    assert row["sehir"] == "ADANA"
    assert row["grup"] == "SEKTÖR"
    assert row["metric_code"] == "ToplamNakdiKrediler"
    assert row["metric_name"] == "Toplam Nakdi Krediler"
    assert row["value_raw"] == "65046605"


def test_finturk_unit_resolution():
    assert resolve_finturk_unit(1, "ToplamNakdiKrediler") == "bin TL"
    assert resolve_finturk_unit(5, "EnerjiKrediPerformansOrani") == "%"
    assert resolve_finturk_unit(6, "SubeSayisi") == "adet"
    assert resolve_finturk_unit(6, "SubeyeDusenNufus") == "kişi"
    assert resolve_finturk_unit(6, "KisiBasiNakdiKredi") == "TL"
    assert resolve_finturk_unit(7, "AltinKredi") == "bin TL"


def test_finturk_quarter_boundaries_and_real_value():
    raw = _flattened_table1_sample()

    result = parse_bddk_finturk(
        raw,
        source_file="bddk_finturk_all_2021_2026.csv",
    )

    assert len(result) == 1

    row = result.iloc[0]

    assert row["series_id"] == (
        "BDDK_FINTURK:t1:toplamnakdikrediler"
    )
    assert row["source"] == "BDDK_FINTURK"

    assert str(row["date"]) == "2021-03-31"
    assert str(row["period_start"]) == "2021-01-01"
    assert str(row["period_end"]) == "2021-03-31"

    assert row["freq"] == "Q"
    assert row["unit"] == "bin TL"
    assert row["value"] == pytest.approx(65046605.0)

    assert json.loads(row["dims"]) == {
        "grup": "SEKTÖR",
        "sehir": "ADANA",
    }


def test_finturk_source_missing_value_is_preserved():
    reconstructed = pd.DataFrame(
        [
            {
                "date": "2021-03-01",
                "year": 2021,
                "month": 3,
                "donem": "2021-3",
                "tablo_no": 5,
                "category": "Oranlar (%)",
                "row_index": 0,
                "eft_kodu": "10001",
                "sehir": "ADIYAMAN",
                "grup": "SEKTÖR",
                "metric_index": 18,
                "metric_code": "DenizcilikKrediPerformansOrani",
                "metric_name": "Denizcilik Kredi Performans Oranı",
                "value_raw": None,
            }
        ]
    )

    result = parse_bddk_finturk(
        reconstructed,
        already_reconstructed=True,
    )

    assert len(result) == 1
    assert pd.isna(result.iloc[0]["value"])
    assert result.iloc[0]["unit"] == "%"


def test_finturk_rejects_non_quarter_month():
    reconstructed = pd.DataFrame(
        [
            {
                "date": "2021-02-01",
                "year": 2021,
                "month": 2,
                "donem": "2021-2",
                "tablo_no": 1,
                "category": "Krediler (Bin TL)",
                "row_index": 0,
                "eft_kodu": "10001",
                "sehir": "ADANA",
                "grup": "SEKTÖR",
                "metric_index": 5,
                "metric_code": "ToplamNakdiKrediler",
                "metric_name": "Toplam Nakdi Krediler",
                "value_raw": "65046605",
            }
        ]
    )

    with pytest.raises(
        ValueError,
        match="not quarter-ending",
    ):
        parse_bddk_finturk(
            reconstructed,
            already_reconstructed=True,
        )


def test_finturk_result_has_unique_observation_keys():
    raw = _flattened_table1_sample()

    result = parse_bddk_finturk(raw)

    assert not result.duplicated(
        ["series_id", "date", "dims"]
    ).any()
