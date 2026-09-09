import json

import pandas as pd
import pytest

from app.modules.bddk.parsers.bddk_monthly import (
    add_parent_context,
    extract_monthly_unit_map,
    monthly_junk_mask,
    parse_bddk_monthly,
)


def _sample_monthly_df():
    return pd.DataFrame(
        [
            # Bilanço header junk
            {
                "date": "2021-01-01",
                "year": 2021,
                "month": 1,
                "category": "Bilanço",
                "row_index": 1,
                "item": "Nakit Değerler",
                "variable": "Bilanço (milyon TL), Dönem:2021/1",
                "value_raw": "Nakit Değerler",
                "value": None,
            },
            {
                "date": "2021-01-01",
                "year": 2021,
                "month": 1,
                "category": "Bilanço",
                "row_index": 1,
                "item": "Nakit Değerler",
                "variable": "Unnamed: 0",
                "value_raw": "Sektör",
                "value": None,
            },

            # Bilanço real values
            {
                "date": "2021-01-01",
                "year": 2021,
                "month": 1,
                "category": "Bilanço",
                "row_index": 1,
                "item": "Nakit Değerler",
                "variable": "TP",
                "value_raw": "16313.305",
                "value": 16313.305,
            },
            {
                "date": "2021-01-01",
                "year": 2021,
                "month": 1,
                "category": "Bilanço",
                "row_index": 1,
                "item": "Nakit Değerler",
                "variable": "Toplam",
                "value_raw": "68733.259",
                "value": 68733.259,
            },

            # Rasyolar structural junk + real
            {
                "date": "2021-01-01",
                "year": 2021,
                "month": 1,
                "category": "Rasyolar",
                "row_index": 1,
                "item": "Örnek Rasyo (%)",
                "variable": "Rasyolar",
                "value_raw": "Örnek Rasyo (%)",
                "value": None,
            },
            {
                "date": "2021-01-01",
                "year": 2021,
                "month": 1,
                "category": "Rasyolar",
                "row_index": 1,
                "item": "Örnek Rasyo (%)",
                "variable": "Rasyo",
                "value_raw": "4.076395",
                "value": 4.076395,
            },

            # Diğer Bilgiler structural junk + real
            {
                "date": "2021-01-01",
                "year": 2021,
                "month": 1,
                "category": "Diğer Bilgiler",
                "row_index": 1,
                "item": "ATM Sayısı",
                "variable": "Diğer Bilgiler",
                "value_raw": "ATM Sayısı",
                "value": None,
            },
            {
                "date": "2021-01-01",
                "year": 2021,
                "month": 1,
                "category": "Diğer Bilgiler",
                "row_index": 1,
                "item": "ATM Sayısı",
                "variable": "Adet",
                "value_raw": "49130",
                "value": 49130.0,
            },
        ]
    )


def test_monthly_junk_detection():
    df = _sample_monthly_df()

    mask = monthly_junk_mask(df)

    assert int(mask.sum()) == 4
    assert int((~mask).sum()) == 4


def test_monthly_unit_resolution():
    df = _sample_monthly_df()

    units = extract_monthly_unit_map(df)

    assert units["Bilanço"] == "milyon TL"
    assert units["Rasyolar"] == "%"
    assert units["Diğer Bilgiler"] == "adet"


def test_monthly_parent_context_for_root_rows():
    df = _sample_monthly_df()
    clean = df.loc[~monthly_junk_mask(df)].copy()

    result = add_parent_context(clean)

    assert set(result["parent_item"]) == {
        "Nakit Değerler",
        "Örnek Rasyo (%)",
        "ATM Sayısı",
    }


def test_monthly_parent_context_for_child_rows():
    df = pd.DataFrame(
        [
            {
                "date": "2021-01-01",
                "year": 2021,
                "month": 1,
                "category": "Mevduat Türler İtibarıyla",
                "row_index": 1,
                "item": "TP Mevduat / Katılım Fonları - Yurt İçi Yerleşik",
                "variable": "Toplam",
                "value_raw": "1492502.178",
                "value": 1492502.178,
            },
            {
                "date": "2021-01-01",
                "year": 2021,
                "month": 1,
                "category": "Mevduat Türler İtibarıyla",
                "row_index": 2,
                "item": "a) Gerçek Kişiler",
                "variable": "Toplam",
                "value_raw": "822827.998",
                "value": 822827.998,
            },
        ]
    )

    result = add_parent_context(df)

    child = result[result["item"] == "a) Gerçek Kişiler"].iloc[0]

    assert (
        child["parent_item"]
        == "TP Mevduat / Katılım Fonları - Yurt İçi Yerleşik"
    )


def test_parse_monthly_real_bddk_values():
    df = _sample_monthly_df()

    result = parse_bddk_monthly(
        df,
        source_file="bddk_monthly_all_2021_2026_precise.csv",
    )

    assert len(result) == 4
    assert set(result["freq"]) == {"M"}
    assert set(result["source"]) == {"BDDK_MONTHLY"}

    nakit = result[
        (result["series_id"] == "BDDK_MONTHLY:bilanco:nakit_degerler")
        & (result["dims"] == '{"variable": "TP"}')
    ].iloc[0]

    assert nakit["value"] == pytest.approx(16313.305)
    assert str(nakit["period_start"]) == "2021-01-01"
    assert str(nakit["period_end"]) == "2021-01-31"
    assert str(nakit["date"]) == "2021-01-31"
    assert nakit["unit"] == "milyon TL"

    ratio = result[
        result["series_id"].str.startswith(
            "BDDK_MONTHLY:rasyolar:"
        )
    ].iloc[0]

    assert ratio["value"] == pytest.approx(4.076395)
    assert ratio["unit"] == "%"

    atm = result[
        result["series_id"]
        == "BDDK_MONTHLY:diger_bilgiler:atm_sayisi"
    ].iloc[0]

    assert atm["value"] == pytest.approx(49130.0)
    assert atm["unit"] == "adet"
    assert json.loads(atm["dims"]) == {
        "variable": "Adet",
    }


def test_parse_monthly_hierarchical_series_identity():
    df = pd.DataFrame(
        [
            {
                "date": "2021-01-01",
                "year": 2021,
                "month": 1,
                "category": "Mevduat Türler İtibarıyla",
                "row_index": 1,
                "item": "TP Mevduat / Katılım Fonları - Yurt İçi Yerleşik",
                "variable": "Mevduat Türler İtibarıyla (milyon TL), Dönem:2021/1",
                "value_raw": None,
                "value": None,
            },
            {
                "date": "2021-01-01",
                "year": 2021,
                "month": 1,
                "category": "Mevduat Türler İtibarıyla",
                "row_index": 1,
                "item": "TP Mevduat / Katılım Fonları - Yurt İçi Yerleşik",
                "variable": "Toplam",
                "value_raw": "1492502.178",
                "value": 1492502.178,
            },
            {
                "date": "2021-01-01",
                "year": 2021,
                "month": 1,
                "category": "Mevduat Türler İtibarıyla",
                "row_index": 2,
                "item": "a) Gerçek Kişiler",
                "variable": "Toplam",
                "value_raw": "822827.998",
                "value": 822827.998,
            },
        ]
    )

    result = parse_bddk_monthly(df)

    child = result[
        result["series_id"].str.endswith(
            ":a_gercek_kisiler"
        )
    ].iloc[0]

    assert child["series_id"] == (
        "BDDK_MONTHLY:"
        "mevduat_turler_itibariyla:"
        "tp_mevduat_katilim_fonlari_yurt_ici_yerlesik:"
        "a_gercek_kisiler"
    )

    assert child["value"] == pytest.approx(822827.998)
    assert child["unit"] == "milyon TL"


def test_monthly_result_has_no_duplicate_observation_keys():
    df = _sample_monthly_df()

    result = parse_bddk_monthly(df)

    assert not result.duplicated(
        ["series_id", "date", "dims"]
    ).any()
