import pandas as pd
import pytest

from app.services.align_service import (
    AlignedPairResult,
    AlignmentPolicy,
    align_pair,
    align_to_monthly,
    generate_alignment_warnings,
    _infer_series_aggregation_method,
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


# =============================================================================
# Unit Tests for Dynamic Pair Alignment & Warning Engine (§5.5)
# =============================================================================

def test_align_pair_daily_and_weekly_sync():
    """Tests aligning daily rate and weekly loan stock on a weekly Friday axis."""
    daily_obs = pd.DataFrame(
        [
            {"series_id": "D:RATE", "source": "EVDS", "date": "2026-01-05", "value": 30.0, "freq": "D"},
            {"series_id": "D:RATE", "source": "EVDS", "date": "2026-01-06", "value": 31.0, "freq": "D"},
            {"series_id": "D:RATE", "source": "EVDS", "date": "2026-01-07", "value": 32.0, "freq": "D"},
            {"series_id": "D:RATE", "source": "EVDS", "date": "2026-01-08", "value": 33.0, "freq": "D"},
            {"series_id": "D:RATE", "source": "EVDS", "date": "2026-01-09", "value": 34.0, "freq": "D"},
        ]
    )

    weekly_obs = pd.DataFrame(
        [
            {"series_id": "W:LOAN", "source": "BDDK_WEEKLY", "date": "2026-01-09", "value": 1000.0, "freq": "W"},
        ]
    )

    res = align_pair(
        daily_obs,
        weekly_obs,
        target_freq="W",
        method_a="mean",
        method_b="last",
    )

    assert isinstance(res, AlignedPairResult)
    assert len(res.df) == 1
    assert str(res.df.iloc[0]["date"]) == "2026-01-09"
    # Average of 30, 31, 32, 33, 34 is 32.0
    assert res.df.iloc[0]["D:RATE"] == 32.0
    assert res.df.iloc[0]["W:LOAN"] == 1000.0

    # Test warnings
    assert any("Frekans uyumsuzluğu" in w for w in res.warnings)
    assert any("ortalama (mean)" in w for w in res.warnings)
    assert any("Veri uydurma (imputation) yapılmadı" in w for w in res.warnings)
    assert any("1 periyot" in w for w in res.warnings)

    # Test tuple unpacking
    df, warnings = res
    assert len(df) == 1
    assert len(warnings) > 0

    # Test to_dict serialization
    d = res.to_dict()
    assert d["common_periods_count"] == 1
    assert d["target_freq"] == "W"
    assert d["data"][0]["value_a"] == 32.0
    assert d["data"][0]["value_b"] == 1000.0


def test_align_pair_auto_target_freq_and_method_inference():
    """Tests automatic downsampling to coarser frequency and semantic method inference."""
    weekly_stock = pd.DataFrame(
        [
            {"series_id": "BDDK_WEEKLY:LOAN", "source": "BDDK_WEEKLY", "date": "2026-01-09", "value": 100.0, "freq": "W", "nature": "stock"},
            {"series_id": "BDDK_WEEKLY:LOAN", "source": "BDDK_WEEKLY", "date": "2026-01-30", "value": 130.0, "freq": "W", "nature": "stock"},
        ]
    )

    monthly_inflation = pd.DataFrame(
        [
            {"series_id": "EVDS:CPI", "source": "EVDS", "date": "2026-01-31", "value": 45.0, "freq": "M", "nature": "stock"},
        ]
    )

    # Without specifying target_freq or methods -> should choose 'M', 'last' for weekly stock, 'native' for monthly
    res = align_pair(weekly_stock, monthly_inflation)

    assert res.target_freq == "M"
    assert len(res.df) == 1
    assert str(res.df.iloc[0]["date"]) == "2026-01-31"
    assert res.df.iloc[0]["BDDK_WEEKLY:LOAN"] == 130.0
    assert res.df.iloc[0]["EVDS:CPI"] == 45.0


def test_align_pair_quarterly_sparse_preserves_quarter_ends_only():
    """Quarterly matching retains only common quarter ends without imputation."""
    monthly_obs = pd.DataFrame(
        [
            {"series_id": "M:SERIES", "source": "EVDS", "date": "2026-01-31", "value": 10.0, "freq": "M"},
            {"series_id": "M:SERIES", "source": "EVDS", "date": "2026-02-28", "value": 20.0, "freq": "M"},
            {"series_id": "M:SERIES", "source": "EVDS", "date": "2026-03-31", "value": 30.0, "freq": "M"},
        ]
    )

    quarterly_obs = pd.DataFrame(
        [
            {"series_id": "Q:FINTURK", "source": "BDDK_FINTURK", "date": "2026-03-31", "value": 500.0, "freq": "Q", "nature": "stock"},
        ]
    )

    res = align_pair(monthly_obs, quarterly_obs, target_freq="M", quarterly_policy="sparse")

    # Only March 31 matches
    assert len(res.df) == 1
    assert str(res.df.iloc[0]["date"]) == "2026-03-31"
    assert res.df.iloc[0]["M:SERIES"] == 30.0
    assert res.df.iloc[0]["Q:FINTURK"] == 500.0
    assert any("çeyreklik veriler yalnızca çeyrek sonlarında bırakıldı" in w for w in res.warnings)


def test_align_pair_raw_cumulative_uses_last():
    assert _infer_series_aggregation_method("RAW:YTD", "ANY", "M", "stock", None, "ytd") == "last"


def test_align_pair_periodic_flow_uses_sum():
    assert _infer_series_aggregation_method("RAW:YTD_periodic", "ANY", "M", "flow", None, "none") == "sum"


def test_align_pair_real_silver_duckdb():
    """End-to-end integration test querying two real series from silver.duckdb."""
    from pathlib import Path
    silver_db = Path(__file__).resolve().parents[3] / "data" / "silver" / "silver.duckdb"
    if not silver_db.exists():
        pytest.skip("silver.duckdb does not exist")

    # Pair Daily USD rate with Weekly Credit Interest Rate
    res = align_pair("EVDS:TP.DK.USD.A.YTL", "EVDS:TP.KTF10", silver_db_path=silver_db)

    assert res.target_freq == "W"
    assert res.common_periods_count > 200
    assert len(res.df) == res.common_periods_count
    assert "EVDS:TP.DK.USD.A.YTL" in res.df.columns
    assert "EVDS:TP.KTF10" in res.df.columns
    assert len(res.warnings) >= 3
