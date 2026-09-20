from __future__ import annotations

import duckdb

from backend.app.tools.anomaly_detection import AnomalyDetectionTool
from backend.app.tools.change_detection import ChangeDetectionTool
from backend.app.tools.series_catalog_search import SeriesCatalogSearchTool


SERIES_ID = "HEALTH_MOH:hospital_beds_total"


def test_health_series_exists_in_canonical_silver():
    con = duckdb.connect("data/silver/silver.duckdb", read_only=True)
    try:
        row = con.execute(
            """
            SELECT source, freq, unit, COUNT(*) AS n
            FROM observations
            WHERE series_id = ?
            GROUP BY source, freq, unit
            """,
            [SERIES_ID],
        ).fetchone()
    finally:
        con.close()

    assert row == ("HEALTH_MOH", "Y", "adet", 6)


def test_health_series_is_semantically_discoverable():
    tool = SeriesCatalogSearchTool()

    result = tool.run(
        tool.Input(
            query="Türkiye toplam hastane yatağı sayısı",
            top_k=5,
        )
    )

    assert result.success is True
    assert result.found_in_lakehouse is True
    assert result.matches
    assert result.matches[0].series_id == SERIES_ID


def test_health_yearly_change_detection_is_frequency_aware():
    tool = ChangeDetectionTool()

    result = tool.run(
        tool.Input(
            series_id=SERIES_ID,
            start_date="2023-01-01",
            end_date="2024-12-31",
        )
    )

    assert result.success is True
    assert len(result.rows) == 2

    row_2024 = result.rows[-1]

    assert row_2024["value"] == 268359.0
    assert row_2024["mom_pct_change"] is None
    assert row_2024["yoy_abs_change"] == 1765.0
    assert abs(row_2024["yoy_pct_change"] - 0.006620554100992521) < 1e-12
    assert row_2024["source"] == "HEALTH_MOH"
    assert row_2024["nature"] == "stock"
    assert row_2024["unit"] == "adet"


def test_health_series_runs_through_existing_anomaly_tool():
    tool = AnomalyDetectionTool()

    result = tool.run(
        tool.Input(
            series_id=SERIES_ID,
            metric="value",
            method="robust",
            start_date="2002-01-01",
            end_date="2024-12-31",
        )
    )

    assert result.success is True
    assert result.data_source == "lakehouse"
    assert result.n_observations == 6


def test_finance_monthly_regression_still_works():
    tool = ChangeDetectionTool()

    result = tool.run(
        tool.Input(
            series_id="BDDK_MONTHLY:tuketici_kredileri:tuketici_kredileri_konut",
            dimension="Toplam",
            start_date="2024-11-01",
            end_date="2024-12-31",
        )
    )

    assert result.success is True
    assert len(result.rows) == 2

    december = result.rows[-1]

    assert december["unit"] == "milyon TL"
    assert december["nature"] == "stock"
    assert december["mom_pct_change"] is not None
    assert december["yoy_pct_change"] is not None
