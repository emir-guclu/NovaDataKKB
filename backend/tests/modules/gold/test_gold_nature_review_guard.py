import pandas as pd
import pytest

from app.modules.gold.review_guard import reviewed_series_ids, require_reviewed_series


def test_reviewed_series_ids_excludes_unreviewed():
    meta = pd.DataFrame([
        {"series_id": "reviewed", "nature_reviewed": True},
        {"series_id": "pending", "nature_reviewed": False},
    ])
    assert reviewed_series_ids(meta) == {"reviewed"}


def test_require_reviewed_series_fails_for_unreviewed_dependency():
    meta = pd.DataFrame([
        {"series_id": "reviewed", "nature_reviewed": True},
        {"series_id": "pending", "nature_reviewed": False},
    ])
    with pytest.raises(ValueError, match="nature_reviewed is not True"):
        require_reviewed_series(meta, ["reviewed", "pending"], "test_gold")


def test_periodic_change_excludes_unreviewed_series(tmp_path):
    from app.modules.gold.build_periodic_change import build_gold_periodic_change

    obs = pd.DataFrame([
        {"date": "2026-01-31", "series_id": "reviewed", "value": 100.0, "source": "EVDS", "unit": "%", "dims": "{}"},
        {"date": "2026-02-28", "series_id": "reviewed", "value": 110.0, "source": "EVDS", "unit": "%", "dims": "{}"},
        {"date": "2026-01-31", "series_id": "pending", "value": 200.0, "source": "EVDS", "unit": "%", "dims": "{}"},
        {"date": "2026-02-28", "series_id": "pending", "value": 220.0, "source": "EVDS", "unit": "%", "dims": "{}"},
    ])
    meta = pd.DataFrame([
        {"series_id": "reviewed", "nature": "rate", "nature_reviewed": True},
        {"series_id": "pending", "nature": "rate", "nature_reviewed": False},
    ])

    obs_path = tmp_path / "observations.parquet"
    meta_path = tmp_path / "series_metadata.parquet"
    out_path = tmp_path / "gold_periodic_change.parquet"
    obs.to_parquet(obs_path, index=False)
    meta.to_parquet(meta_path, index=False)

    build_gold_periodic_change(obs_path, meta_path, out_path)

    result = pd.read_parquet(out_path)
    assert set(result["series_id"].unique()) == {"reviewed"}
    assert "pending" not in set(result["series_id"])
