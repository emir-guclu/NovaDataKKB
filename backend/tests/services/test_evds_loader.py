"""Unit tests for the on-demand EVDS series loader service."""

import json
from pathlib import Path
from unittest.mock import MagicMock

import duckdb
import pyarrow.parquet as pq
import pytest

from app.services.evds_loader import (
    _normalize_series_code,
    load_evds_series,
)


@pytest.fixture
def mock_evds_client():
    client = MagicMock()
    # Sample EVDS API raw response (monthly)
    client.get_data.return_value = [
        {"Tarih": "2023-1", "TP_DK_USD_A_YTL": "18.75"},
        {"Tarih": "2023-2", "TP_DK_USD_A_YTL": "18.82"},
        {"Tarih": "2023-3", "TP_DK_USD_A_YTL": "19.01"},
    ]
    client.get_series_metadata.return_value = [
        {
            "SERIE_CODE": "TP.DK.USD.A.YTL",
            "SERIE_NAME": "ABD Doları (Döviz Alış)",
            "FREQUENCY_STR": "AYLIK",
            "DATAGROUP_NAME": "Döviz Kurları",
            "BIRIMI": "TL",
            "NOTE": "Aylık ortalama kur",
            "TAG": ["kur", "usd"],
        }
    ]
    return client


@pytest.fixture
def canonical_silver_db(tmp_path: Path):
    db_path = tmp_path / "silver.duckdb"
    con = duckdb.connect(str(db_path))
    con.execute(
        """
        CREATE TABLE observations (
            series_id VARCHAR,
            source VARCHAR,
            date DATE,
            period_start DATE,
            period_end DATE,
            value DOUBLE,
            freq VARCHAR,
            unit VARCHAR,
            dims JSON,
            source_file VARCHAR
        );
        CREATE TABLE series_metadata (
            series_id VARCHAR,
            source VARCHAR,
            series_code VARCHAR,
            series_name VARCHAR,
            category VARCHAR,
            freq VARCHAR,
            unit VARCHAR,
            description VARCHAR,
            tags VARCHAR[],
            accumulation VARCHAR,
            is_cumulative BOOLEAN,
            nature VARCHAR,
            alignment_override VARCHAR
        );
        """
    )
    con.close()
    return db_path


def test_normalize_series_code():
    assert _normalize_series_code("TP.DK.USD.A.YTL") == "TP.DK.USD.A.YTL"
    assert _normalize_series_code("EVDS:TP.DK.USD.A.YTL") == "TP.DK.USD.A.YTL"
    assert _normalize_series_code("  EVDS:TP.DK.EUR.A.YTL  ") == "TP.DK.EUR.A.YTL"


def test_load_evds_series_without_silver_db(tmp_path: Path, mock_evds_client):
    bronze_dir = tmp_path / "bronze"
    silver_dir = tmp_path / "silver"
    meta_raw = bronze_dir / "metadata_raw.json"

    result = load_evds_series(
        series_code="EVDS:TP.DK.USD.A.YTL",
        client=mock_evds_client,
        add_to_silver=False,
        bronze_dir=bronze_dir,
        silver_dir=silver_dir,
        metadata_raw_path=meta_raw,
    )

    assert result["status"] == "success"
    assert result["series_id"] == "EVDS:TP.DK.USD.A.YTL"
    assert result["series_code"] == "TP.DK.USD.A.YTL"
    assert result["series_name"] == "ABD Doları (Döviz Alış)"
    assert result["freq"] == "M"
    assert result["unit"] == "TL"
    assert result["rows_count"] == 3
    assert result["first_date"] == "2023-01-31"
    assert result["last_date"] == "2023-03-31"
    assert result["latest_value"] == 19.01
    assert result["added_to_silver"] is False
    assert len(result["preview"]) == 3

    # Check Bronze JSON written
    raw_json = bronze_dir / "TP.DK.USD.A.YTL.json"
    assert raw_json.exists()
    with open(raw_json, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert len(data) == 3

    # Check Silver Parquet written
    obs_pq = silver_dir / "observations.parquet"
    meta_pq = silver_dir / "series_metadata.parquet"
    assert obs_pq.exists()
    assert meta_pq.exists()

    obs_table = pq.read_table(obs_pq)
    assert obs_table.num_rows == 3

    meta_table = pq.read_table(meta_pq)
    assert meta_table.num_rows == 1


def test_load_evds_series_with_silver_db(
    tmp_path: Path, mock_evds_client, canonical_silver_db: Path
):
    bronze_dir = tmp_path / "bronze"
    silver_dir = tmp_path / "silver"
    meta_raw = bronze_dir / "metadata_raw.json"

    result = load_evds_series(
        series_code="TP.DK.USD.A.YTL",
        client=mock_evds_client,
        add_to_silver=True,
        bronze_dir=bronze_dir,
        silver_dir=silver_dir,
        silver_db_path=canonical_silver_db,
        metadata_raw_path=meta_raw,
    )

    assert result["status"] == "success"
    assert result["added_to_silver"] is True

    # Validate in DuckDB
    con = duckdb.connect(str(canonical_silver_db))
    try:
        # Check observations count
        obs_count = con.execute(
            "SELECT COUNT(*) FROM observations WHERE series_id = 'EVDS:TP.DK.USD.A.YTL'"
        ).fetchone()[0]
        assert obs_count == 3

        # Check metadata count
        meta_count = con.execute(
            "SELECT COUNT(*) FROM series_metadata WHERE series_id = 'EVDS:TP.DK.USD.A.YTL'"
        ).fetchone()[0]
        assert meta_count == 1

        meta_row = con.execute(
            """
            SELECT nature, alignment_override
            FROM series_metadata
            WHERE series_id = 'EVDS:TP.DK.USD.A.YTL'
            """
        ).fetchone()

        assert meta_row[0] == "price"
        assert meta_row[1] is None

        # Check canonical rule: date == period_end
        date_check = con.execute(
            "SELECT COUNT(*) FROM observations WHERE series_id = 'EVDS:TP.DK.USD.A.YTL' AND date != period_end"
        ).fetchone()[0]
        assert date_check == 0

        # Check unit and dims column type
        row = con.execute(
            """
            SELECT date, period_start, period_end, value, unit, dims
            FROM observations
            WHERE series_id = 'EVDS:TP.DK.USD.A.YTL'
            ORDER BY date DESC
            LIMIT 1
            """
        ).fetchone()

        assert str(row[0]) == "2023-03-31"
        assert str(row[1]) == "2023-03-01"
        assert str(row[2]) == "2023-03-31"
        assert row[3] == 19.01
        assert row[4] == "TL"
    finally:
        con.close()


def test_load_evds_series_idempotency(
    tmp_path: Path, mock_evds_client, canonical_silver_db: Path
):
    bronze_dir = tmp_path / "bronze"
    silver_dir = tmp_path / "silver"
    meta_raw = bronze_dir / "metadata_raw.json"

    # Call twice
    for _ in range(2):
        result = load_evds_series(
            series_code="TP.DK.USD.A.YTL",
            client=mock_evds_client,
            add_to_silver=True,
            bronze_dir=bronze_dir,
            silver_dir=silver_dir,
            silver_db_path=canonical_silver_db,
            metadata_raw_path=meta_raw,
        )
        assert result["status"] == "success"

    # Should not duplicate records in DuckDB
    con = duckdb.connect(str(canonical_silver_db))
    try:
        obs_count = con.execute(
            "SELECT COUNT(*) FROM observations WHERE series_id = 'EVDS:TP.DK.USD.A.YTL'"
        ).fetchone()[0]
        assert obs_count == 3

        meta_count = con.execute(
            "SELECT COUNT(*) FROM series_metadata WHERE series_id = 'EVDS:TP.DK.USD.A.YTL'"
        ).fetchone()[0]
        assert meta_count == 1
    finally:
        con.close()

    # Should not duplicate in local parquet
    obs_pq = silver_dir / "observations.parquet"
    assert pq.read_table(obs_pq).num_rows == 3


def test_load_evds_series_empty_error(tmp_path: Path):
    mock_client = MagicMock()
    mock_client.get_data.return_value = []

    with pytest.raises(ValueError, match="EVDS returned no observation data"):
        load_evds_series(
            series_code="INVALID.SERIES",
            client=mock_client,
            bronze_dir=tmp_path / "bronze",
            silver_dir=tmp_path / "silver",
        )


def test_unclassified_evds_cannot_be_added_to_canonical_silver(tmp_path, canonical_silver_db):
    client = MagicMock()
    client.get_data.return_value = [{"Tarih": "2023-1", "TP_UNKNOWN_SERIES": "1.0"}]
    client.get_series_metadata.return_value = [{
        "SERIE_CODE": "TP.UNKNOWN.SERIES",
        "SERIE_NAME": "Unknown Official Series",
        "FREQUENCY_STR": "AYLIK",
        "DATAGROUP_NAME": "Tanimsiz Yeni Kategori",
        "BIRIMI": "TL",
        "NOTE": "Unknown test category",
        "TAG": [],
    }]
    with pytest.raises(ValueError, match="EVDS:TP.UNKNOWN.SERIES"):
        load_evds_series(
            series_code="TP.UNKNOWN.SERIES",
            client=client,
            add_to_silver=True,
            bronze_dir=tmp_path / "bronze",
            silver_dir=tmp_path / "silver",
            silver_db_path=canonical_silver_db,
            metadata_raw_path=tmp_path / "bronze" / "metadata_raw.json",
        )
