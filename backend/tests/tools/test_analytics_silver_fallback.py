import pytest
from pathlib import Path

from backend.app.tools.anomaly_detection import AnomalyDetectionTool
from backend.app.tools.causality_check import CausalityCheckTool
from backend.app.tools.change_detection import ChangeDetectionTool
from backend.app.tools.elasticity_and_sensitivity_analyzer import (
    ElasticityAndSensitivityAnalyzerTool,
)
from backend.app.tools.real_value_deflator import RealValueDeflatorTool
from backend.app.tools.turning_point_and_cycle_detector import (
    TurningPointAndCycleDetectorTool,
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SILVER_DB = PROJECT_ROOT / "data" / "silver" / "silver.duckdb"
GOLD_PARQUET = PROJECT_ROOT / "data" / "gold" / "gold_periodic_change.parquet"

pytestmark = pytest.mark.skipif(
    not SILVER_DB.exists() or not GOLD_PARQUET.exists(),
    reason="silver.duckdb veya gold_periodic_change.parquet bulunamadi",
)

SILVER_ONLY_SERIES = "EVDS:TP.TRY.MT02.S"
GOLD_SERIES = "BDDK_MONTHLY:tuketici_kredileri:tuketici_kredileri_konut"


def test_causality_check_with_silver_fallback():
    tool = CausalityCheckTool()
    # Test value metric
    result = tool.run(
        tool.Input(
            series_id_a=GOLD_SERIES,
            series_id_b=SILVER_ONLY_SERIES,
            dimension_a="Toplam",
            metric="value",
            start_date="2023-01-01",
            end_date="2026-06-30",
        )
    )
    assert result.success is True, f"Failed: {result.error}"
    assert result.error is None
    assert result.correlation_coefficient is not None
    assert result.n_observations >= 10

    # Test mom_pct_change metric on silver-only series
    result_mom = tool.run(
        tool.Input(
            series_id_a=GOLD_SERIES,
            series_id_b=SILVER_ONLY_SERIES,
            dimension_a="Toplam",
            metric="mom_pct_change",
            start_date="2023-01-01",
            end_date="2026-06-30",
        )
    )
    assert result_mom.success is True, f"Failed mom: {result_mom.error}"
    assert result_mom.correlation_coefficient is not None


def test_elasticity_analyzer_with_silver_fallback():
    tool = ElasticityAndSensitivityAnalyzerTool()
    result = tool.run(
        tool.Input(
            dependent_series_id=GOLD_SERIES,
            independent_series_id=SILVER_ONLY_SERIES,
            dependent_dimension="Toplam",
            method="log_log_regression",
            start_date="2023-01-01",
            end_date="2026-06-30",
        )
    )
    assert result.success is True, f"Failed: {result.error}"
    assert result.error is None
    assert result.elasticity_coefficient is not None
    assert result.sample_size >= 10


def test_real_value_deflator_with_silver_fallback():
    tool = RealValueDeflatorTool()
    result = tool.run(
        tool.Input(
            nominal_series_id=SILVER_ONLY_SERIES,
            deflator_series_id="TP.GENENDEKS.T1",
            start_date="2023-01-01",
            end_date="2026-06-30",
        )
    )
    assert result.success is True, f"Failed: {result.error}"
    assert result.error is None
    assert result.real_growth_pct is not None


def test_turning_point_detector_with_silver_fallback():
    tool = TurningPointAndCycleDetectorTool()
    result = tool.run(
        tool.Input(
            series_id=SILVER_ONLY_SERIES,
            start_date="2021-01-01",
            end_date="2026-06-30",
        )
    )
    assert result.success is True, f"Failed: {result.error}"
    assert result.error is None
    assert result.current_phase is not None


def test_change_detection_with_silver_fallback():
    tool = ChangeDetectionTool()
    result = tool.run(
        tool.Input(
            series_id=SILVER_ONLY_SERIES,
            start_date="2023-01-01",
            end_date="2026-06-30",
        )
    )
    assert result.success is True, f"Failed: {result.error}"
    assert result.error is None
    assert len(result.rows) > 0
    # The second row onwards should have mom_pct_change computed
    has_mom = any(r.get("mom_pct_change") is not None for r in result.rows)
    assert has_mom is True


def test_anomaly_detection_with_silver_fallback():
    tool = AnomalyDetectionTool()
    # Test value metric
    result = tool.run(
        tool.Input(
            series_id=SILVER_ONLY_SERIES,
            metric="value",
            start_date="2023-01-01",
            end_date="2026-06-30",
        )
    )
    assert result.success is True, f"Failed value: {result.error}"
    assert result.error is None
    assert result.n_observations > 0

    # Test mom_pct_change metric
    result_mom = tool.run(
        tool.Input(
            series_id=SILVER_ONLY_SERIES,
            metric="mom_pct_change",
            start_date="2023-01-01",
            end_date="2026-06-30",
        )
    )
    assert result_mom.success is True, f"Failed mom: {result_mom.error}"
    assert result_mom.error is None
    assert result_mom.n_observations > 0
