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
    )

    assert policy is not None
    assert policy.method == "last"


def test_evds_weekly_rate_resolves_to_mean():
    policy = resolve_alignment_policy(
        "EVDS:TP.KTF12",
        "EVDS",
        "W",
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
                freq
            FROM series_metadata
            WHERE freq IN ('D', 'W')
            ORDER BY series_id
            """
        ).fetchdf()
    finally:
        con.close()

    policies = build_alignment_policies(metadata)

    assert len(metadata) == 197
    assert len(policies) == 197
    assert set(policies) == set(metadata["series_id"])
