from pathlib import Path

import duckdb

from app.services.alignment_policies import (
    build_alignment_policies,
    resolve_alignment_policy,
)


ROOT = Path(__file__).resolve().parents[3]
DB_PATH = ROOT / "data" / "silver" / "silver.duckdb"


def test_bddk_weekly_resolves_to_last():
    policy = resolve_alignment_policy(
        "BDDK_WEEKLY:krediler:r1:toplam_krediler_2_10",
        "BDDK_WEEKLY",
        "W",
        nature="stock",
    )

    assert policy is not None
    assert policy.method == "last"


def test_evds_weekly_rate_resolves_to_mean():
    policy = resolve_alignment_policy(
        "EVDS:TP.KTF12",
        "EVDS",
        "W",
        nature="rate",
    )

    assert policy is not None
    assert policy.method == "mean"


def test_real_canonical_dw_series_have_complete_policy_coverage():
    con = duckdb.connect(
        str(DB_PATH),
        read_only=True,
    )

    try:
        metadata = con.execute(
            """
            SELECT
                series_id,
                source,
                freq,
                nature,
                alignment_override,
                accumulation
            FROM series_metadata
            WHERE freq IN ('D', 'W')
            ORDER BY series_id
            """
        ).fetchdf()
    finally:
        con.close()

    policies = build_alignment_policies(metadata)

    assert len(metadata) == 212
    assert len(policies) == 212
    assert set(policies) == set(metadata["series_id"])



def test_flow_resolves_to_sum_without_source_heuristic():
    policy = resolve_alignment_policy(
        "SYNTHETIC:FLOW",
        "SOME_NEW_PROVIDER",
        "W",
        nature="flow",
    )

    assert policy is not None
    assert policy.method == "sum"


def test_price_resolves_to_mean_without_keyword_heuristic():
    policy = resolve_alignment_policy(
        "SYNTHETIC:X1",
        "SOME_NEW_PROVIDER",
        "D",
        nature="price",
    )

    assert policy is not None
    assert policy.method == "mean"


def test_alignment_override_can_override_stock_default():
    policy = resolve_alignment_policy(
        "EVDS:TP.APIFON1.IHA",
        "EVDS",
        "D",
        nature="stock",
        alignment_override="mean",
    )

    assert policy is not None
    assert policy.method == "mean"


def test_missing_nature_fails_loudly_with_series_id():
    import pytest

    with pytest.raises(
        ValueError,
        match="EVDS:UNKNOWN",
    ):
        resolve_alignment_policy(
            "EVDS:UNKNOWN",
            "EVDS",
            "D",
            nature=None,
        )


def test_unclassified_nature_fails_loudly_with_series_id():
    import pytest

    with pytest.raises(
        ValueError,
        match="EVDS:UNKNOWN",
    ):
        resolve_alignment_policy(
            "EVDS:UNKNOWN",
            "EVDS",
            "W",
            nature="unclassified",
        )


def test_raw_cumulative_forces_last():
    policy = resolve_alignment_policy("TEST:YTD", "ANY", "W", nature="stock", accumulation="ytd")
    assert policy is not None
    assert policy.method == "last"


def test_periodic_flow_resolves_to_sum():
    policy = resolve_alignment_policy("TEST:YTD_periodic", "ANY", "W", nature="flow", accumulation="none")
    assert policy is not None
    assert policy.method == "sum"
