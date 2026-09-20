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

    # 1. Hiçbiri verilmediğinde reddetmeli
    with pytest.raises(ValidationError):
        RealValueDeflatorTool.Input()  # type: ignore

    # 2. Hem nominal_series_id hem nominal_observations verildiğinde reddetmeli
    with pytest.raises(ValidationError):
        RealValueDeflatorTool.Input(
            nominal_series_id="BDDK_MONTHLY:tuketici_kredileri:tuketici_kredileri_konut",
            nominal_observations=[{"date": "2024-01-01", "value": 100.0}],
        )


def test_real_value_deflator_inline_observations():
    tool = RealValueDeflatorTool()
    # 6 aylık harici tüketici kredi tablosu (2024-01 ile 2024-06 arası)
    observations = [
        {"date": "2024-01-31", "value": 1000.0},
        {"date": "2024-02-29", "value": 1050.0},
        {"date": "2024-03-31", "value": 1100.0},
        {"date": "2024-04-30", "value": 1150.0},
        {"date": "2024-05-31", "value": 1200.0},
        {"date": "2024-06-30", "value": 1250.0},
    ]

    result = tool.run(
        RealValueDeflatorTool.Input(
            nominal_observations=observations,
            deflator_series_id="TP.GENENDEKS.T1",
            start_date="2024-01-01",
            end_date="2024-06-30",
        )
    )

    assert result.success is True
    assert result.data_source == "inline"
    assert result.nominal_series_id == "Harici Nominal Seri"
    assert result.nominal_growth_pct is not None
    assert result.inflation_pct is not None
    assert result.real_growth_pct is not None
    assert result.erosion_amount is not None
    assert result.summary_verdict is not None
    assert result.chart_url is not None
    assert len(result.data_points) == 6


def test_real_value_deflator_inline_day_format_matching():
    tool = RealValueDeflatorTool()
    # Tarihler ayın 1'i olarak verildiğinde (2024-01-01 vb.), Lakehouse CPI ay sonu (2024-01-31) verisiyle
    # ay bazlı fallback (%Y-%m) eşleşebilmeli
    observations = [
        {"date": "2024-01-01", "value": 500000.0},
        {"date": "2024-02-01", "value": 520000.0},
        {"date": "2024-03-01", "value": 540000.0},
        {"date": "2024-04-01", "value": 560000.0},
    ]

    result = tool.run(
        RealValueDeflatorTool.Input(
            nominal_observations=observations,
            deflator_series_id="TP.GENENDEKS.T1",
        )
    )

    assert result.success is True
    assert result.data_source == "inline"
    assert len(result.data_points) == 4
    assert any("ay bazında" in w for w in result.warnings)


def test_real_value_deflator_inline_dimension_warning():
    tool = RealValueDeflatorTool()
    observations = [
        {"date": "2024-01-31", "value": 100.0},
        {"date": "2024-02-29", "value": 105.0},
        {"date": "2024-03-31", "value": 110.0},
    ]
    result = tool.run(
        RealValueDeflatorTool.Input(
            nominal_observations=observations,
            dimension="Toplam",
        )
    )
    assert result.success is True
    assert any("dimension" in w.lower() for w in result.warnings)

