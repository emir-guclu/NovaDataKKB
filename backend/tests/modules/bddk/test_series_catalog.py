import pandas as pd
import pytest

from app.modules.bddk.parsers.series_catalog import (
    build_series_catalog,
    get_accumulation,
)


YTD_SERIES = (
    "BDDK_MONTHLY:kar_zarar:"
    "kredilerden_alinan_faizler_kar_paylari"
)


def test_get_accumulation_for_reviewed_ytd_series():
    assert get_accumulation(YTD_SERIES) == "ytd"


def test_get_accumulation_defaults_to_none():
    assert (
        get_accumulation(
            "BDDK_WEEKLY:krediler:r1:toplam_krediler"
        )
        == "none"
    )

    assert (
        get_accumulation(
            YTD_SERIES + "_periodic"
        )
        == "none"
    )


def test_build_series_catalog_metadata():
    observations = pd.DataFrame(
        [
            {
                "series_id": YTD_SERIES,
                "source": "BDDK_MONTHLY",
                "freq": "M",
                "unit": "milyon TL",
            },
            {
                "series_id": YTD_SERIES,
                "source": "BDDK_MONTHLY",
                "freq": "M",
                "unit": "milyon TL",
            },
            {
                "series_id": YTD_SERIES + "_periodic",
                "source": "BDDK_MONTHLY",
                "freq": "M",
                "unit": "milyon TL",
            },
        ]
    )

    catalog = build_series_catalog(observations)

    assert len(catalog) == 2
    assert not catalog["series_id"].duplicated().any()

    raw = catalog[
        catalog["series_id"] == YTD_SERIES
    ].iloc[0]

    periodic = catalog[
        catalog["series_id"] == YTD_SERIES + "_periodic"
    ].iloc[0]

    assert raw["accumulation"] == "ytd"
    assert bool(raw["is_cumulative"]) is True

    assert periodic["accumulation"] == "none"
    assert bool(periodic["is_cumulative"]) is False


def test_catalog_rejects_conflicting_series_metadata():
    observations = pd.DataFrame(
        [
            {
                "series_id": "TEST:series",
                "source": "BDDK_MONTHLY",
                "freq": "M",
                "unit": "milyon TL",
            },
            {
                "series_id": "TEST:series",
                "source": "BDDK_MONTHLY",
                "freq": "M",
                "unit": "%",
            },
        ]
    )

    with pytest.raises(
        ValueError,
        match="multiple source/freq/unit",
    ):
        build_series_catalog(observations)
