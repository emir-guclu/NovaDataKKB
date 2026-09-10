import pandas as pd
import pytest

from app.services.align_service import (
    AlignmentPolicy,
    align_to_monthly,
)


def _metadata(rows):
    return pd.DataFrame(rows)


def test_weekly_stock_uses_last_observation():
    observations = pd.DataFrame(
        [
            {
                "series_id": "W:STOCK",
                "source": "BDDK_WEEKLY",
                "date": "2026-01-09",
                "value": 100.0,
                "freq": "W",
                "unit": "milyon TL",
                "dims": "{}",
            },
            {
                "series_id": "W:STOCK",
                "source": "BDDK_WEEKLY",
                "date": "2026-01-30",
                "value": 130.0,
                "freq": "W",
                "unit": "milyon TL",
                "dims": "{}",
            },
        ]
    )

    metadata = _metadata(
        [
            {
                "series_id": "W:STOCK",
                "accumulation": "none",
            }
        ]
    )

    result = align_to_monthly(
        observations,
        metadata,
        {
            "W:STOCK": AlignmentPolicy(
                method="last"
            )
        },
    )

    assert len(result) == 1
    assert result.iloc[0]["value"] == 130.0
    assert str(result.iloc[0]["date"]) == "2026-01-31"


def test_weekly_flow_uses_sum():
    observations = pd.DataFrame(
        [
            {
                "series_id": "W:FLOW",
                "source": "EVDS",
                "date": "2026-01-09",
                "value": 10.0,
                "freq": "W",
                "unit": "adet",
                "dims": "{}",
            },
            {
                "series_id": "W:FLOW",
                "source": "EVDS",
                "date": "2026-01-16",
                "value": 20.0,
                "freq": "W",
                "unit": "adet",
                "dims": "{}",
            },
        ]
    )

    metadata = _metadata(
        [
            {
                "series_id": "W:FLOW",
                "accumulation": "none",
            }
        ]
    )

    result = align_to_monthly(
        observations,
        metadata,
        {
            "W:FLOW": AlignmentPolicy(
                method="sum"
            )
        },
    )

    assert result.iloc[0]["value"] == 30.0


def test_monthly_series_is_preserved():
    observations = pd.DataFrame(
        [
            {
                "series_id": "M:TEST",
                "source": "BDDK_MONTHLY",
                "date": "2026-01-31",
                "value": 50.0,
                "freq": "M",
                "unit": "%",
                "dims": "{}",
            }
        ]
    )

    metadata = _metadata(
        [
            {
                "series_id": "M:TEST",
                "accumulation": "none",
            }
        ]
    )

    result = align_to_monthly(
        observations,
        metadata,
        {},
    )

    assert result.iloc[0]["value"] == 50.0
    assert result.iloc[0]["alignment_method"] == "native"


def test_raw_ytd_series_is_excluded():
    observations = pd.DataFrame(
        [
            {
                "series_id": "BDDK:YTD",
                "source": "BDDK_MONTHLY",
                "date": "2026-01-31",
                "value": 100.0,
                "freq": "M",
                "unit": "milyon TL",
                "dims": "{}",
            }
        ]
    )

    metadata = _metadata(
        [
            {
                "series_id": "BDDK:YTD",
                "accumulation": "ytd",
            }
        ]
    )

    result = align_to_monthly(
        observations,
        metadata,
        {},
    )

    assert result.empty


def test_quarterly_is_sparse_by_default():
    observations = pd.DataFrame(
        [
            {
                "series_id": "Q:TEST",
                "source": "BDDK_FINTURK",
                "date": "2026-03-31",
                "value": 100.0,
                "freq": "Q",
                "unit": "bin TL",
                "dims": '{"province":"Ankara"}',
            },
            {
                "series_id": "Q:TEST",
                "source": "BDDK_FINTURK",
                "date": "2026-06-30",
                "value": 120.0,
                "freq": "Q",
                "unit": "bin TL",
                "dims": '{"province":"Ankara"}',
            },
        ]
    )

    metadata = _metadata(
        [
            {
                "series_id": "Q:TEST",
                "accumulation": "none",
            }
        ]
    )

    result = align_to_monthly(
        observations,
        metadata,
        {},
    )

    assert len(result) == 2
    assert list(result["date"].astype(str)) == [
        "2026-03-31",
        "2026-06-30",
    ]


def test_quarterly_ffill_is_explicit():
    observations = pd.DataFrame(
        [
            {
                "series_id": "Q:TEST",
                "source": "BDDK_FINTURK",
                "date": "2026-03-31",
                "value": 100.0,
                "freq": "Q",
                "unit": "bin TL",
                "dims": "{}",
            },
            {
                "series_id": "Q:TEST",
                "source": "BDDK_FINTURK",
                "date": "2026-06-30",
                "value": 120.0,
                "freq": "Q",
                "unit": "bin TL",
                "dims": "{}",
            },
        ]
    )

    metadata = _metadata(
        [
            {
                "series_id": "Q:TEST",
                "accumulation": "none",
            }
        ]
    )

    result = align_to_monthly(
        observations,
        metadata,
        {},
        quarterly_policy="ffill",
    )

    assert list(result["date"].astype(str)) == [
        "2026-03-31",
        "2026-04-30",
        "2026-05-31",
        "2026-06-30",
    ]

    assert list(result["value"]) == [
        100.0,
        100.0,
        100.0,
        120.0,
    ]

    assert list(result["is_imputed"]) == [
        False,
        True,
        True,
        False,
    ]


def test_weekly_series_requires_explicit_policy():
    observations = pd.DataFrame(
        [
            {
                "series_id": "W:NO_POLICY",
                "source": "EVDS",
                "date": "2026-01-09",
                "value": 1.0,
                "freq": "W",
                "unit": "%",
                "dims": "{}",
            }
        ]
    )

    metadata = _metadata(
        [
            {
                "series_id": "W:NO_POLICY",
                "accumulation": "none",
            }
        ]
    )

    with pytest.raises(
        ValueError,
        match="Missing alignment policy",
    ):
        align_to_monthly(
            observations,
            metadata,
            {},
        )
