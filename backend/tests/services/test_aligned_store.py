import duckdb
import pandas as pd
import pytest

from app.services.aligned_store import upsert_single_series_to_aligned_duckdb


def _create_aligned_db(path):
    con = duckdb.connect(str(path))
    con.execute(
        """
        CREATE TABLE observations (
            series_id VARCHAR,
            source VARCHAR,
            date DATE,
            value DOUBLE,
            source_freq VARCHAR,
            aligned_freq VARCHAR,
            unit VARCHAR,
            dims JSON,
            alignment_method VARCHAR,
            is_imputed BOOLEAN
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
            nature_reviewed BOOLEAN,
            alignment_override VARCHAR
        );
        """
    )
    con.close()


def test_aligned_single_series_upsert(tmp_path):
    db_path = tmp_path / "aligned.duckdb"
    _create_aligned_db(db_path)

    series_id = "EVDS:TP.TEST.MONTHLY"

    aligned = pd.DataFrame([{
        "series_id": series_id,
        "source": "EVDS",
        "date": pd.Timestamp("2023-01-31"),
        "value": 10.0,
        "source_freq": "M",
        "aligned_freq": "M",
        "unit": "Adet",
        "dims": "{}",
        "alignment_method": "identity",
        "is_imputed": False,
    }])

    metadata = pd.DataFrame([{
        "series_id": series_id,
        "source": "EVDS",
        "series_code": "TP.TEST.MONTHLY",
        "series_name": "Test",
        "category": "test",
        "freq": "M",
        "unit": "Adet",
        "description": None,
        "tags": [],
        "accumulation": "none",
        "is_cumulative": False,
        "nature": "flow",
        "nature_reviewed": True,
        "alignment_override": None,
    }])

    upsert_single_series_to_aligned_duckdb(
        db_path=db_path,
        series_id=series_id,
        aligned=aligned,
        metadata=metadata,
    )

    con = duckdb.connect(str(db_path))
    try:
        assert con.execute(
            "SELECT COUNT(*) FROM observations WHERE series_id = ?",
            [series_id],
        ).fetchone()[0] == 1

        row = con.execute(
            "SELECT nature, nature_reviewed FROM series_metadata WHERE series_id = ?",
            [series_id],
        ).fetchone()

        assert row == ("flow", True)
    finally:
        con.close()


def test_aligned_store_rejects_stale_schema(tmp_path):
    db_path = tmp_path / "aligned.duckdb"
    con = duckdb.connect(str(db_path))
    con.execute(
        """
        CREATE TABLE observations (
            series_id VARCHAR
        );
        CREATE TABLE series_metadata (
            series_id VARCHAR,
            nature VARCHAR
        );
        """
    )
    con.close()

    aligned = pd.DataFrame([{
        "series_id": "EVDS:TEST"
    }])
    metadata = pd.DataFrame([{
        "series_id": "EVDS:TEST"
    }])

    with pytest.raises(RuntimeError, match="nature_reviewed is missing"):
        upsert_single_series_to_aligned_duckdb(
            db_path=db_path,
            series_id="EVDS:TEST",
            aligned=aligned,
            metadata=metadata,
        )
