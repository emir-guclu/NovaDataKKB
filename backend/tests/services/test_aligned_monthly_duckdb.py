from pathlib import Path

import duckdb


ROOT = Path(__file__).resolve().parents[3]
DB_PATH = (
    ROOT
    / "data"
    / "aligned"
    / "monthly"
    / "aligned.duckdb"
)


def _connect():
    assert DB_PATH.exists(), (
        f"Aligned DuckDB not found: {DB_PATH}"
    )
    return duckdb.connect(
        str(DB_PATH),
        read_only=True,
    )


def test_aligned_output_contains_rows():
    con = _connect()

    try:
        count = con.execute(
            """
            SELECT COUNT(*)
            FROM observations
            """
        ).fetchone()[0]
    finally:
        con.close()

    assert count > 0


def test_all_rows_are_monthly_aligned():
    con = _connect()

    try:
        bad_count = con.execute(
            """
            SELECT COUNT(*)
            FROM observations
            WHERE aligned_freq <> 'M'
               OR aligned_freq IS NULL
            """
        ).fetchone()[0]
    finally:
        con.close()

    assert bad_count == 0


def test_no_duplicate_aligned_keys():
    con = _connect()

    try:
        duplicate_count = con.execute(
            """
            SELECT COUNT(*)
            FROM (
                SELECT
                    series_id,
                    date,
                    dims,
                    COUNT(*) AS n
                FROM observations
                GROUP BY
                    series_id,
                    date,
                    dims
                HAVING COUNT(*) > 1
            )
            """
        ).fetchone()[0]
    finally:
        con.close()

    assert duplicate_count == 0


def test_every_observation_has_metadata():
    con = _connect()

    try:
        missing_count = con.execute(
            """
            SELECT COUNT(*)
            FROM observations o
            LEFT JOIN series_metadata m
              ON o.series_id = m.series_id
            WHERE m.series_id IS NULL
            """
        ).fetchone()[0]
    finally:
        con.close()

    assert missing_count == 0


def test_metadata_has_no_orphans():
    con = _connect()

    try:
        orphan_count = con.execute(
            """
            SELECT COUNT(*)
            FROM series_metadata m
            LEFT JOIN observations o
              ON m.series_id = o.series_id
            WHERE o.series_id IS NULL
            """
        ).fetchone()[0]
    finally:
        con.close()

    assert orphan_count == 0


def test_raw_cumulative_series_are_excluded():
    con = _connect()

    try:
        cumulative_count = con.execute(
            """
            SELECT COUNT(DISTINCT o.series_id)
            FROM observations o
            JOIN series_metadata m
              ON o.series_id = m.series_id
            WHERE m.accumulation <> 'none'
            """
        ).fetchone()[0]
    finally:
        con.close()

    assert cumulative_count == 0


def test_quarterly_rows_are_sparse_not_imputed():
    con = _connect()

    try:
        imputed_count = con.execute(
            """
            SELECT COUNT(*)
            FROM observations
            WHERE source_freq = 'Q'
              AND is_imputed = TRUE
            """
        ).fetchone()[0]

        bad_method_count = con.execute(
            """
            SELECT COUNT(*)
            FROM observations
            WHERE source_freq = 'Q'
              AND alignment_method <> 'quarter_end_sparse'
            """
        ).fetchone()[0]
    finally:
        con.close()

    assert imputed_count == 0
    assert bad_method_count == 0


def test_weekly_bddk_uses_last():
    con = _connect()

    try:
        bad_count = con.execute(
            """
            SELECT COUNT(*)
            FROM observations
            WHERE source = 'BDDK_WEEKLY'
              AND alignment_method <> 'last'
            """
        ).fetchone()[0]
    finally:
        con.close()

    assert bad_count == 0


def test_evds_daily_and_weekly_use_mean():
    con = _connect()

    try:
        bad_count = con.execute(
            """
            SELECT COUNT(*)
            FROM observations
            WHERE source = 'EVDS'
              AND source_freq IN ('D', 'W')
              AND alignment_method <> 'mean'
            """
        ).fetchone()[0]
    finally:
        con.close()

    assert bad_count == 0


def test_dims_column_is_native_json():
    con = _connect()

    try:
        dims_type = con.execute(
            """
            SELECT data_type
            FROM information_schema.columns
            WHERE table_name = 'observations'
              AND column_name = 'dims'
            """
        ).fetchone()[0]
    finally:
        con.close()

    assert dims_type.upper() == "JSON"
