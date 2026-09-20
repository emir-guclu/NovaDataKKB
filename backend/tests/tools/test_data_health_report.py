from __future__ import annotations

import pytest
from backend.app.tools.data_health_report import DataHealthReportTool


@pytest.fixture
def tool() -> DataHealthReportTool:
    return DataHealthReportTool()


def test_data_health_lakehouse_bddk_series(tool: DataHealthReportTool) -> None:
    # Test with a known BDDK series in lakehouse
    series_id = "BDDK_MONTHLY:tuketici_kredileri:tuketici_kredileri_konut"
    output = tool.run(tool.Input(series_id=series_id))
    
    assert output.success is True
    assert output.error is None
    assert output.series_id is not None
    assert output.observation_count > 0
    assert output.start_date is not None
    assert output.end_date is not None
    assert output.start_date <= output.end_date
    assert output.missing_count >= 0
    assert 0.0 <= output.missing_pct <= 100.0
    assert output.health_score >= 0.0
    assert output.health_status in ("EXCELLENT", "GOOD", "FAIR", "WARNING")
    assert isinstance(output.is_cumulative, bool)
    assert output.alignment_policy in ("last", "sum", "mean", "override")
    assert len(output.summary_sentence) > 0


def test_data_health_lakehouse_evds_series(tool: DataHealthReportTool) -> None:
    # Test with a known EVDS series in silver.duckdb
    series_id = "EVDS:TP.AB.B1"
    output = tool.run(tool.Input(series_id=series_id))
    
    assert output.success is True
    assert output.error is None
    assert output.source == "EVDS"
    assert output.observation_count > 0
    assert output.start_date is not None
    assert output.end_date is not None
    assert output.missing_pct == 0.0
    assert output.health_score >= 90.0
    assert output.health_status == "EXCELLENT"


def test_data_health_gold_table_column_lineage(tool: DataHealthReportTool) -> None:
    # Test with gold_table and gold_column
    output = tool.run(
        tool.Input(
            gold_table="gold_housing_credit_market",
            gold_column="konut_kredisi_faiz_orani",
        )
    )
    
    assert output.success is True
    assert output.error is None
    assert output.observation_count > 0
    assert output.lineage is not None
    assert output.lineage.get("gold_table") == "gold_housing_credit_market"
    assert output.lineage.get("gold_column") == "konut_kredisi_faiz_orani"
    assert output.lineage.get("source_series_id") is not None
    assert output.lineage.get("alignment_method") is not None


def test_data_health_inline_observations_clean(tool: DataHealthReportTool) -> None:
    # Test clean inline observations with 0% missing
    observations = [
        {"date": "2024-01-01", "value": 100.0},
        {"date": "2024-02-01", "value": 105.5},
        {"date": "2024-03-01", "value": 110.2},
        {"date": "2024-04-01", "value": 115.0},
        {"date": "2024-05-01", "value": 120.0},
        {"date": "2024-06-01", "value": 125.0},
    ]
    output = tool.run(tool.Input(observations=observations))
    
    assert output.success is True
    assert output.observation_count == 6
    assert output.start_date == "2024-01-01"
    assert output.end_date == "2024-06-01"
    assert output.missing_count == 0
    assert output.missing_pct == 0.0
    assert output.health_score == 100.0
    assert output.health_status == "EXCELLENT"
    assert "100" in output.summary_sentence or "EXCELLENT" in output.summary_sentence


def test_data_health_inline_observations_with_missing(tool: DataHealthReportTool) -> None:
    # Test inline observations with missing / null / nan values
    observations = [
        {"date": "2024-01-01", "value": 100.0},
        {"date": "2024-02-01", "value": None},
        {"date": "2024-03-01", "value": float("nan")},
        {"date": "2024-04-01", "value": 115.0},
    ]
    output = tool.run(tool.Input(observations=observations))
    
    assert output.success is True
    assert output.observation_count == 4
    assert output.missing_count == 2
    assert output.missing_pct == 50.0
    assert output.health_score <= 50.0
    assert output.health_status == "WARNING"


def test_data_health_unknown_series_error(tool: DataHealthReportTool) -> None:
    # Unknown series should gracefully return success=False with clear error
    output = tool.run(tool.Input(series_id="NON_EXISTENT_SERIES_12345"))
    
    assert output.success is False
    assert output.error is not None
    assert "bulunamadi" in output.error.lower() or "not found" in output.error.lower()


def test_data_health_no_input_error(tool: DataHealthReportTool) -> None:
    # Running without series_id, gold_table, or observations
    output = tool.run(tool.Input())
    
    assert output.success is False
    assert output.error is not None
