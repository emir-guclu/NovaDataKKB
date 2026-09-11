"""Unit and integrity tests for EVDS Silver Transformation Pipeline (§3.4 & §5.4)."""

import calendar
from datetime import date, timedelta
from pathlib import Path
import pandas as pd
import pytest

from app.modules.evds.transformer import (
    compute_period_boundaries,
    parse_evds_date,
    resolve_canonical_freq,
    clean_observation_value,
    slugify_turkish,
    build_series_dimension_row,
    transform_silver_evds,
    OBSERVATIONS_SCHEMA,
    SERIES_METADATA_SCHEMA,
)

SILVER_DIR = Path("data/silver/evds")
OBS_PATH = SILVER_DIR / "observations.parquet"
META_PATH = SILVER_DIR / "series_metadata.parquet"


def test_slugify_turkish():
    assert slugify_turkish("Döviz Kurları") == "doviz_kurlari"
    assert slugify_turkish("Tüketici Fiyat Endeksi (TÜFE)") == "tuketici_fiyat_endeksi_tufe"
    assert slugify_turkish("") == "genel"
    assert slugify_turkish(None) == "genel"


def test_resolve_canonical_freq():
    assert resolve_canonical_freq("GÜNLÜK") == "D"
    assert resolve_canonical_freq("HAFTALIK(CUMA)") == "W"
    assert resolve_canonical_freq("HAFTALIK") == "W"
    assert resolve_canonical_freq("AYLIK") == "M"
    assert resolve_canonical_freq("3 AYLIK") == "Q"
    assert resolve_canonical_freq("YILLIK") == "Y"
    assert resolve_canonical_freq(None) == "D"


def test_parse_evds_date():
    d1, f1 = parse_evds_date("04-01-2021")
    assert d1 == date(2021, 1, 4)
    assert f1 == "daily"

    d2, f2 = parse_evds_date("2021-1")
    assert d2 == date(2021, 1, 1)
    assert f2 == "monthly"

    d3, f3 = parse_evds_date("2021-Q2")
    assert d3 == date(2021, 4, 1)
    assert f3 == "quarterly"

    with pytest.raises(ValueError):
        parse_evds_date("invalid-date")


def test_period_boundaries_computation():
    # Daily
    dt_d = date(2021, 1, 4)
    p_start, p_end = compute_period_boundaries(dt_d, "D")
    assert p_start == dt_d
    assert p_end == dt_d

    # Weekly: Friday Jan 8, 2021 -> Monday Jan 4, 2021
    dt_w = date(2021, 1, 8)
    p_start, p_end = compute_period_boundaries(dt_w, "W")
    assert p_start == date(2021, 1, 4)  # Monday
    assert p_end == date(2021, 1, 8)    # Friday
    assert p_start.weekday() == 0       # ISO Monday
    assert p_end.weekday() == 4         # Friday

    # Monthly: Jan 2021 -> Jan 1 to Jan 31
    dt_m = date(2021, 1, 1)
    p_start, p_end = compute_period_boundaries(dt_m, "M")
    assert p_start == date(2021, 1, 1)
    assert p_end == date(2021, 1, 31)

    # Monthly: Feb 2024 (leap year) -> Feb 1 to Feb 29
    dt_m2 = date(2024, 2, 1)
    p_start, p_end = compute_period_boundaries(dt_m2, "M")
    assert p_start == date(2024, 2, 1)
    assert p_end == date(2024, 2, 29)


def test_clean_observation_value():
    assert clean_observation_value("26,76") == 26.76
    assert clean_observation_value("100.5") == 100.5
    assert clean_observation_value(123) == 123.0
    assert clean_observation_value("-") is None
    assert clean_observation_value("ND") is None
    assert clean_observation_value("") is None
    assert clean_observation_value(None) is None


@pytest.mark.skipif(not OBS_PATH.exists() or not META_PATH.exists(), reason="Parquet files not generated yet")
def test_observations_parquet_schema_and_types():
    df = pd.read_parquet(OBS_PATH)
    expected_cols = ["series_id", "source", "date", "period_start", "period_end", "value", "freq", "dims"]
    assert list(df.columns) == expected_cols

    # Types and non-null constraints
    assert (df["source"] == "EVDS").all()
    assert df["dims"].apply(lambda s: isinstance(s, str) and s.startswith("{") and s.endswith("}")).all()
    assert df["series_id"].str.startswith("EVDS:").all()
    assert df["freq"].isin(["D", "W", "M", "Q", "Y"]).all()
    assert df["date"].notna().all()
    assert df["period_start"].notna().all()
    assert df["period_end"].notna().all()


@pytest.mark.skipif(not OBS_PATH.exists() or not META_PATH.exists(), reason="Parquet files not generated yet")
def test_series_metadata_parquet_schema_and_types():
    meta = pd.read_parquet(META_PATH)
    expected_cols = [
        "series_id", "series_code", "series_name", "category", "tcmb_category",
        "tcmb_datagroup", "freq", "unit", "description", "tags", "source",
        "nature", "nature_reviewed", "alignment_override"
    ]
    assert list(meta.columns) == expected_cols
    assert (meta["source"] == "EVDS").all()
    assert meta["series_id"].str.startswith("EVDS:").all()
    assert meta["series_code"].notna().all()
    assert meta["series_name"].notna().all()
    assert meta["freq"].isin(["D", "W", "M", "Q", "Y"]).all()


@pytest.mark.skipif(not OBS_PATH.exists() or not META_PATH.exists(), reason="Parquet files not generated yet")
def test_cross_table_integrity_and_freq_synchronization():
    """Verifies §3.4: observations and series_metadata have identical series_id sets and synchronized freq."""
    obs = pd.read_parquet(OBS_PATH)
    meta = pd.read_parquet(META_PATH)

    obs_series_set = set(obs["series_id"].unique())
    meta_series_set = set(meta["series_id"].unique())

    # 1. Exact series_id match across both tables
    assert obs_series_set == meta_series_set
    assert len(meta_series_set) > 0, "Dimension table must contain at least one series"

    # 2. Synchronized freq match for every single series
    obs_freq_map = obs.groupby("series_id")["freq"].first().to_dict()
    meta_freq_map = meta.set_index("series_id")["freq"].to_dict()

    for s_id, o_freq in obs_freq_map.items():
        m_freq = meta_freq_map.get(s_id)
        assert o_freq == m_freq, f"Freq mismatch for {s_id}: obs has '{o_freq}', meta has '{m_freq}'"


@pytest.mark.skipif(not OBS_PATH.exists(), reason="Observations parquet not generated yet")
def test_weekly_series_iso_boundaries():
    """Verifies that for weekly series, period_start is Monday and period_end is Friday."""
    obs = pd.read_parquet(OBS_PATH)
    weekly_obs = obs[obs["freq"] == "W"]
    assert len(weekly_obs) > 0

    p_starts = pd.to_datetime(weekly_obs["period_start"])
    p_ends = pd.to_datetime(weekly_obs["period_end"])
    dates = pd.to_datetime(weekly_obs["date"])

    # All period_start must be Monday (dayofweek == 0)
    assert (p_starts.dt.dayofweek == 0).all()

    # All period_end must be Friday (dayofweek == 4)
    assert (p_ends.dt.dayofweek == 4).all()

    # period_end must match observation date (Friday)
    assert (p_ends == dates).all()


@pytest.mark.skipif(not OBS_PATH.exists(), reason="Observations parquet not generated yet")
def test_deterministic_sorting():
    """Verifies that observations.parquet is strictly sorted by (series_id ASC, date ASC)."""
    obs = pd.read_parquet(OBS_PATH)
    sorted_obs = obs.sort_values(by=["series_id", "date"]).reset_index(drop=True)
    pd.testing.assert_frame_equal(obs[["series_id", "date"]], sorted_obs[["series_id", "date"]])


def test_reviewed_evds_category_sets_nature_reviewed_true():
    row = build_series_dimension_row(
        "TP.DK.USD.A.YTL",
        {
            "SERIE_NAME": "USD",
            "FREQUENCY_STR": "AYLIK",
            "DATAGROUP_NAME": "Döviz Kurları",
            "BIRIMI": "Türk lirası",
        },
    )
    assert row["nature"] == "price"
    assert row["nature_reviewed"] is True


def test_unknown_evds_official_metadata_classification_is_unreviewed():
    row = build_series_dimension_row(
        "TP.NEW.FLOW",
        {
            "SERIE_NAME": "New Official Series",
            "FREQUENCY_STR": "AYLIK",
            "DATAGROUP_NAME": "Yeni Resmi Kategori",
            "BIRIMI": "Adet",
            "DEFAULT_AGG_METHOD_STR": "KÜMÜLATİF",
        },
    )
    assert row["nature"] == "flow"
    assert row["nature_reviewed"] is False


def test_unknown_ambiguous_evds_stays_unclassified_and_unreviewed():
    row = build_series_dimension_row(
        "TP.NEW.AMBIGUOUS",
        {
            "SERIE_NAME": "Ambiguous Official Series",
            "FREQUENCY_STR": "AYLIK",
            "DATAGROUP_NAME": "Yeni Resmi Kategori",
            "BIRIMI": "bin TL",
            "DEFAULT_AGG_METHOD_STR": "BİTİŞ",
        },
    )
    assert row["nature"] == "unclassified"
    assert row["nature_reviewed"] is False


def test_single_series_parquet_upsert_rolls_back_when_second_write_fails(tmp_path, monkeypatch):
    import app.modules.evds.transformer as transformer_module

    silver_dir = tmp_path / "silver"
    series_id = "EVDS:TP.TEST.ROLLBACK"
    observations = [{
        "series_id": series_id,
        "source": "EVDS",
        "date": pd.Timestamp("2023-01-31").date(),
        "period_start": pd.Timestamp("2023-01-01").date(),
        "period_end": pd.Timestamp("2023-01-31").date(),
        "value": 1.0,
        "freq": "M",
        "unit": "Adet",
        "dims": "{}",
        "source_file": "TP.TEST.ROLLBACK.json",
    }]
    metadata = {
        "series_id": series_id,
        "series_code": "TP.TEST.ROLLBACK",
        "series_name": "Rollback Test",
        "category": "test",
        "tcmb_category": None,
        "tcmb_datagroup": None,
        "freq": "M",
        "unit": "Adet",
        "description": None,
        "tags": [],
        "source": "EVDS",
        "nature": "flow",
        "nature_reviewed": False,
        "alignment_override": None,
    }

    transformer_module.upsert_single_series_to_silver_parquet(
        series_id, observations, metadata, silver_dir=silver_dir
    )

    obs_path = silver_dir / "observations.parquet"
    meta_path = silver_dir / "series_metadata.parquet"
    obs_before = obs_path.read_bytes()
    meta_before = meta_path.read_bytes()

    original_write = transformer_module.write_parquet_atomic
    calls = {"count": 0}

    def fail_on_second_write(table, target_path):
        calls["count"] += 1
        if calls["count"] == 2:
            raise RuntimeError("injected metadata parquet failure")
        return original_write(table, target_path)

    monkeypatch.setattr(transformer_module, "write_parquet_atomic", fail_on_second_write)

    changed_observations = [dict(observations[0], value=99.0)]

    with pytest.raises(RuntimeError, match="injected metadata parquet failure"):
        transformer_module.upsert_single_series_to_silver_parquet(
            series_id, changed_observations, metadata, silver_dir=silver_dir
        )

    assert obs_path.read_bytes() == obs_before
    assert meta_path.read_bytes() == meta_before
