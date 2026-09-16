from pathlib import Path
import pytest
from backend.app.tools.real_value_deflator import RealValueDeflatorTool


def test_real_value_deflator_math_logic():
    tool = RealValueDeflatorTool()
    # Mock edilmiş veya gerçek verilerle çalışma testi
    # BDDK tüketici kredileri konut veya EVDS serisi
    result = tool.run(
        RealValueDeflatorTool.Input(
            nominal_series_id="BDDK_MONTHLY:tuketici_kredileri:tuketici_kredileri_konut",
            deflator_series_id="TP.GENENDEKS.T1",
            dimension="Toplam",
            start_date="2024-01-01",
            end_date="2024-12-31",
        )
    )

    assert result.success is True
    assert result.nominal_growth_pct is not None
    assert result.inflation_pct is not None
    assert result.real_growth_pct is not None
    assert result.summary_verdict is not None
    assert result.chart_url is not None
    assert result.chart_url.startswith("/static/charts/deflator_")
    assert len(result.data_points) > 0


def test_real_value_deflator_series_not_found():
    tool = RealValueDeflatorTool()
    result = tool.run(
        RealValueDeflatorTool.Input(
            nominal_series_id="NON_EXISTENT_SERIES_XYZ",
            deflator_series_id="TP.GENENDEKS.T1",
        )
    )
    assert result.success is False
    assert "bulunamadi" in result.error.lower()


def test_real_value_deflator_schema_validation():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        # nominal_series_id zorunlu alandır, eksik verildiğinde reddetmeli
        RealValueDeflatorTool.Input()  # type: ignore
