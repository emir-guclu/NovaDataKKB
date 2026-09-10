import pytest

from app.services.series_nature import (
    alignment_method_for_nature,
    classify_series_nature,
)


def test_raw_ytd_is_stock_and_periodic_is_flow():
    raw_id = (
        "BDDK_MONTHLY:kar_zarar:"
        "kredilerden_alinan_faizler_kar_paylari"
    )
    periodic_id = raw_id + "_periodic"

    raw_nature, raw_override = classify_series_nature(
        series_id=raw_id,
        source="BDDK_MONTHLY",
        category="kar_zarar",
        accumulation="ytd",
    )

    periodic_nature, periodic_override = classify_series_nature(
        series_id=periodic_id,
        source="BDDK_MONTHLY",
        category="kar_zarar",
        accumulation="none",
    )

    assert raw_nature == "stock"
    assert raw_override is None

    assert periodic_nature == "flow"
    assert periodic_override is None


def test_natures_map_to_expected_alignment():
    assert alignment_method_for_nature("stock") == "last"
    assert alignment_method_for_nature("flow") == "sum"
    assert alignment_method_for_nature("rate") == "mean"
    assert alignment_method_for_nature("price") == "mean"


def test_alignment_override_wins():
    assert (
        alignment_method_for_nature(
            "stock",
            "mean",
        )
        == "mean"
    )


def test_unclassified_alignment_fails():
    with pytest.raises(ValueError):
        alignment_method_for_nature("unclassified")


def test_unknown_dynamic_evds_stays_unclassified():
    nature, override = classify_series_nature(
        series_id="EVDS:TP.NEW.UNKNOWN",
        source="EVDS",
        category="brand_new_category",
        accumulation="none",
    )

    assert nature == "unclassified"
    assert override is None


def test_evds_mixed_funding_category_is_series_specific():
    category = (
        "tcmb_net_fonlamasi_ve_tcmb_"
        "agirlikli_ortalama_fonlama_maliyeti"
    )

    funding_nature, funding_override = classify_series_nature(
        series_id="EVDS:TP.APIFON1.IHA",
        source="EVDS",
        category=category,
        accumulation="none",
    )

    cost_nature, cost_override = classify_series_nature(
        series_id="EVDS:TP.APIFON4",
        source="EVDS",
        category=category,
        accumulation="none",
    )

    assert funding_nature == "stock"
    assert funding_override == "mean"

    assert cost_nature == "rate"
    assert cost_override is None


def test_finturk_ratio_category_is_rate():
    nature, override = classify_series_nature(
        series_id="BDDK_FINTURK:t5:test",
        source="BDDK_FINTURK",
        category="t5",
        accumulation="none",
    )

    assert nature == "rate"
    assert override is None
