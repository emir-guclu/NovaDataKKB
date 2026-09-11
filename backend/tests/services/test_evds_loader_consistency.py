import logging

import duckdb
import pyarrow.parquet as pq
import pytest
from unittest.mock import MagicMock

import app.services.evds_loader as evds_loader


def _client():
    client = MagicMock()
    client.get_data.return_value = [
        {"Tarih": "2023-1", "TP_DK_USD_A_YTL": "18.75"},
        {"Tarih": "2023-2", "TP_DK_USD_A_YTL": "18.82"},
        {"Tarih": "2023-3", "TP_DK_USD_A_YTL": "19.01"},
    ]
    client.get_series_metadata.return_value = [{
        "SERIE_CODE": "TP.DK.USD.A.YTL",
        "SERIE_NAME": "ABD Dolari",
        "FREQUENCY_STR": "AYLIK",
        "DATAGROUP_NAME": "Döviz Kurları",
        "BIRIMI": "TL",
        "NOTE": "Test",
        "TAG": [],
    }]
    return client


def _create_dbs(tmp_path):
    silver = tmp_path / "silver.duckdb"
    aligned = tmp_path / "aligned.duckdb"

    con = duckdb.connect(str(silver))
    con.execute("""
        CREATE TABLE observations (
            series_id VARCHAR, source VARCHAR, date DATE,
            period_start DATE, period_end DATE, value DOUBLE,
            freq VARCHAR, unit VARCHAR, dims JSON, source_file VARCHAR
        );
        CREATE TABLE series_metadata (
            series_id VARCHAR, source VARCHAR, series_code VARCHAR,
            series_name VARCHAR, category VARCHAR, freq VARCHAR,
            unit VARCHAR, description VARCHAR, tags VARCHAR[],
            accumulation VARCHAR, is_cumulative BOOLEAN, nature VARCHAR,
            nature_reviewed BOOLEAN, alignment_override VARCHAR
        );
    """)
    con.close()

    con = duckdb.connect(str(aligned))
    con.execute("""
        CREATE TABLE observations (
            series_id VARCHAR, source VARCHAR, date DATE, value DOUBLE,
            source_freq VARCHAR, aligned_freq VARCHAR, unit VARCHAR,
            dims JSON, alignment_method VARCHAR, is_imputed BOOLEAN
        );
        CREATE TABLE series_metadata (
            series_id VARCHAR, source VARCHAR, series_code VARCHAR,
            series_name VARCHAR, category VARCHAR, freq VARCHAR,
            unit VARCHAR, description VARCHAR, tags VARCHAR[],
            accumulation VARCHAR, is_cumulative BOOLEAN, nature VARCHAR,
            nature_reviewed BOOLEAN, alignment_override VARCHAR
        );
    """)
    con.close()

    return silver, aligned


def test_counts_match_across_parquet_silver_and_aligned(tmp_path):
    silver_db, aligned_db = _create_dbs(tmp_path)
    silver_dir = tmp_path / "evds"

    result = evds_loader.load_evds_series(
        series_code="TP.DK.USD.A.YTL",
        client=_client(),
        add_to_silver=True,
        bronze_dir=tmp_path / "bronze",
        silver_dir=silver_dir,
        silver_db_path=silver_db,
        aligned_db_path=aligned_db,
        metadata_raw_path=tmp_path / "bronze" / "metadata_raw.json",
    )

    assert result["added_to_silver"] is True
    assert result["added_to_aligned"] is True

    series_id = "EVDS:TP.DK.USD.A.YTL"

    parquet_obs = pq.read_table(silver_dir / "observations.parquet").to_pandas()
    parquet_meta = pq.read_table(silver_dir / "series_metadata.parquet").to_pandas()

    assert len(parquet_obs[parquet_obs["series_id"] == series_id]) == 3
    assert len(parquet_meta[parquet_meta["series_id"] == series_id]) == 1

    con = duckdb.connect(str(silver_db))
    try:
        assert con.execute(
            "SELECT COUNT(*) FROM observations WHERE series_id = ?", [series_id]
        ).fetchone()[0] == 3
        assert con.execute(
            "SELECT COUNT(*) FROM series_metadata WHERE series_id = ?", [series_id]
        ).fetchone()[0] == 1
    finally:
        con.close()

    con = duckdb.connect(str(aligned_db))
    try:
        assert con.execute(
            "SELECT COUNT(*) FROM observations WHERE series_id = ?", [series_id]
        ).fetchone()[0] == 3
        assert con.execute(
            "SELECT COUNT(*) FROM series_metadata WHERE series_id = ?", [series_id]
        ).fetchone()[0] == 1
    finally:
        con.close()


def test_aligned_failure_is_logged_loudly(tmp_path, monkeypatch, caplog):
    silver_db, aligned_db = _create_dbs(tmp_path)
    series_id = "EVDS:TP.DK.USD.A.YTL"

    def fail_aligned_write(**kwargs):
        raise RuntimeError("injected aligned write failure")

    monkeypatch.setattr(
        evds_loader,
        "upsert_single_series_to_aligned_duckdb",
        fail_aligned_write,
    )

    with caplog.at_level(logging.CRITICAL):
        with pytest.raises(RuntimeError, match="injected aligned write failure"):
            evds_loader.load_evds_series(
                series_code="TP.DK.USD.A.YTL",
                client=_client(),
                add_to_silver=True,
                bronze_dir=tmp_path / "bronze",
                silver_dir=tmp_path / "evds",
                silver_db_path=silver_db,
                aligned_db_path=aligned_db,
                metadata_raw_path=tmp_path / "bronze" / "metadata_raw.json",
            )

    assert "cross-layer inconsistency is possible" in caplog.text

    con = duckdb.connect(str(silver_db))
    try:
        assert con.execute(
            "SELECT COUNT(*) FROM observations WHERE series_id = ?", [series_id]
        ).fetchone()[0] == 3
    finally:
        con.close()

    con = duckdb.connect(str(aligned_db))
    try:
        assert con.execute(
            "SELECT COUNT(*) FROM observations WHERE series_id = ?", [series_id]
        ).fetchone()[0] == 0
    finally:
        con.close()
