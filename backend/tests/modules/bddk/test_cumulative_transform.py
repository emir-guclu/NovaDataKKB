import json

import pandas as pd
import pytest

from app.modules.bddk.parsers.cumulative_transform import (
    add_periodic_series,
)


YTD_SERIES = (
    "BDDK_MONTHLY:kar_zarar:"
    "kredilerden_alinan_faizler_kar_paylari"
)


def _sample_observations():
    dims = json.dumps(
        {"variable": "TP"},
        ensure_ascii=False,
        sort_keys=True,
    )

    return pd.DataFrame(
        [
            {
                "series_id": YTD_SERIES,
                "source": "BDDK_MONTHLY",
                "date": "2021-01-31",
                "period_start": "2021-01-01",
                "period_end": "2021-01-31",
                "value": 25382.899,
                "freq": "M",
                "unit": "milyon TL",
                "dims": dims,
                "source_file": "monthly.csv",
            },
            {
                "series_id": YTD_SERIES,
                "source": "BDDK_MONTHLY",
                "date": "2021-02-28",
                "period_start": "2021-02-01",
                "period_end": "2021-02-28",
                "value": 49154.549,
                "freq": "M",
                "unit": "milyon TL",
                "dims": dims,
                "source_file": "monthly.csv",
            },
            {
                "series_id": YTD_SERIES,
                "source": "BDDK_MONTHLY",
                "date": "2021-03-31",
                "period_start": "2021-03-01",
                "period_end": "2021-03-31",
                "value": 77130.808,
                "freq": "M",
                "unit": "milyon TL",
                "dims": dims,
                "source_file": "monthly.csv",
            },
            {
                "series_id": YTD_SERIES,
                "source": "BDDK_MONTHLY",
                "date": "2022-01-31",
                "period_start": "2022-01-01",
                "period_end": "2022-01-31",
                "value": 39274.998,
                "freq": "M",
                "unit": "milyon TL",
                "dims": dims,
                "source_file": "monthly.csv",
            },
        ]
    )


def test_add_periodic_series_preserves_raw_and_adds_periodic():
    original = _sample_observations()

    result = add_periodic_series(original)

    assert len(result) == 8

    assert YTD_SERIES in set(result["series_id"])
    assert YTD_SERIES + "_periodic" in set(
        result["series_id"]
    )

    assert not result.duplicated(
        ["series_id", "date", "dims"]
    ).any()


def test_periodic_values_match_real_bddk_differences():
    result = add_periodic_series(
        _sample_observations()
    )

    periodic = (
        result[
            result["series_id"]
            == YTD_SERIES + "_periodic"
        ]
        .sort_values("date")
        .reset_index(drop=True)
    )

    assert periodic.loc[0, "value"] == pytest.approx(
        25382.899
    )

    assert periodic.loc[1, "value"] == pytest.approx(
        23771.650
    )

    assert periodic.loc[2, "value"] == pytest.approx(
        27976.259
    )

    # YTD resets at the beginning of a new year.
    assert periodic.loc[3, "value"] == pytest.approx(
        39274.998
    )
