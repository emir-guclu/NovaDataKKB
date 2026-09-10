from pathlib import Path

import duckdb


ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "data" / "silver" / "silver.duckdb"


def _connect():
    assert DB_PATH.exists(), f"Canonical Silver DB not found: {DB_PATH}"
    return duckdb.connect(str(DB_PATH), read_only=True)


def test_canonical_date_equals_period_end():
    con = _connect()
    try:
        count = con.execute(
            """
            SELECT COUNT(*)
            FROM observations
            WHERE date <> period_end
            """
        ).fetchone()[0]

        assert count == 0
    finally:
        con.close()


def test_observations_have_metadata():
    con = _connect()
    try:
        missing = con.execute(
            """
            SELECT COUNT(*)
            FROM (
                SELECT DISTINCT series_id
                FROM observations

                EXCEPT

                SELECT series_id
                FROM series_metadata
            )
            """
        ).fetchone()[0]

        assert missing == 0
    finally:
        con.close()


def test_metadata_has_no_orphans():
    con = _connect()
    try:
        orphan = con.execute(
            """
            SELECT COUNT(*)
            FROM (
                SELECT series_id
                FROM series_metadata

                EXCEPT

                SELECT DISTINCT series_id
                FROM observations
            )
            """
        ).fetchone()[0]

        assert orphan == 0
    finally:
        con.close()


def test_no_duplicate_canonical_observations():
    con = _connect()
    try:
        duplicate_groups = con.execute(
            """
            SELECT COUNT(*)
            FROM (
                SELECT
                    series_id,
                    date,
                    CAST(dims AS VARCHAR) AS dims_key,
                    COUNT(*) AS n
                FROM observations
                GROUP BY
                    series_id,
                    date,
                    CAST(dims AS VARCHAR)
                HAVING COUNT(*) > 1
            )
            """
        ).fetchone()[0]

        assert duplicate_groups == 0
    finally:
        con.close()


def test_dims_column_is_native_json():
    con = _connect()
    try:
        dims_type = con.execute(
            """
            SELECT column_type
            FROM (
                DESCRIBE observations
            )
            WHERE column_name = 'dims'
            """
        ).fetchone()[0]

        assert dims_type == "JSON"
    finally:
        con.close()


def test_finturk_uses_canonical_geography_keys():
    con = _connect()
    try:
        leaking_source_keys = con.execute(
            """
            SELECT COUNT(*)
            FROM observations
            WHERE source = 'BDDK_FINTURK'
              AND (
                    json_extract(dims, '$.sehir') IS NOT NULL
                 OR json_extract(dims, '$.grup') IS NOT NULL
              )
            """
        ).fetchone()[0]

        assert leaking_source_keys == 0
    finally:
        con.close()


def test_finturk_provinces_have_plate_codes():
    con = _connect()
    try:
        missing_plate = con.execute(
            """
            SELECT COUNT(*)
            FROM observations
            WHERE source = 'BDDK_FINTURK'
              AND json_extract_string(dims, '$.geo_level') = 'province'
              AND (
                    json_extract_string(dims, '$.province') IS NULL
                 OR json_extract_string(dims, '$.plate_code') IS NULL
              )
            """
        ).fetchone()[0]

        assert missing_plate == 0
    finally:
        con.close()


def test_adıyaman_is_canonicalized_correctly():
    con = _connect()
    try:
        row = con.execute(
            """
            SELECT DISTINCT
                json_extract_string(dims, '$.province') AS province,
                json_extract_string(dims, '$.plate_code') AS plate_code
            FROM observations
            WHERE source = 'BDDK_FINTURK'
              AND json_extract_string(dims, '$.plate_code') = '02'
            LIMIT 1
            """
        ).fetchone()

        assert row is not None
        assert row[0] == "Adıyaman"
        assert row[1] == "02"
    finally:
        con.close()
