import pytest
from backend.app.tools.turning_point_and_cycle_detector import TurningPointAndCycleDetectorTool


def test_turning_point_and_cycle_detector_success():
    tool = TurningPointAndCycleDetectorTool()
    result = tool.run(
        TurningPointAndCycleDetectorTool.Input(
            series_id="BDDK_MONTHLY:tuketici_kredileri:tuketici_kredileri_konut",
            dimension="Toplam",
            smoothing_window=3,
            min_cycle_length=3,
            start_date="2022-01-01",
            end_date="2024-12-31",
        )
    )

    assert result.success is True
    assert result.current_phase is not None
    assert result.duration_months >= 0
    assert result.max_drawdown_pct is not None
    assert result.chart_url is not None
    assert result.chart_url.startswith("/static/charts/cycle_")
    assert isinstance(result.peaks, list)
    assert isinstance(result.troughs, list)


def test_turning_point_and_cycle_detector_series_not_found():
    tool = TurningPointAndCycleDetectorTool()
    result = tool.run(
        TurningPointAndCycleDetectorTool.Input(
            series_id="NON_EXISTENT_SERIES_999",
        )
    )
    assert result.success is False
    assert "bulunamadi" in result.error.lower()


def test_turning_point_and_cycle_detector_schema_validation():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        # series_id zorunludur
        TurningPointAndCycleDetectorTool.Input()  # type: ignore
