import pytest
from backend.app.tools.elasticity_and_sensitivity_analyzer import ElasticityAndSensitivityAnalyzerTool


def test_elasticity_analyzer_log_log_regression():
    tool = ElasticityAndSensitivityAnalyzerTool()
    # Konut kredisi vs Politika faizi veya ihtiyaç kredisi faizi
    # EVDS serileri ve BDDK serileri aligned parquet içinde mevcut
    result = tool.run(
        ElasticityAndSensitivityAnalyzerTool.Input(
            dependent_series_id="BDDK_MONTHLY:tuketici_kredileri:tuketici_kredileri_konut",
            independent_series_id="EVDS:TP.GENENDEKS.T1",
            dependent_dimension="Toplam",
            method="log_log_regression",
            start_date="2023-01-01",
            end_date="2024-12-31",
        )
    )

    assert result.success is True
    assert result.elasticity_coefficient is not None
    assert result.r_squared is not None
    assert result.classification is not None
    assert result.interpretation is not None
    assert result.chart_url is not None
    assert result.chart_url.startswith("/static/charts/elasticity_")
    assert result.sample_size > 5


def test_elasticity_analyzer_arc_elasticity():
    tool = ElasticityAndSensitivityAnalyzerTool()
    result = tool.run(
        ElasticityAndSensitivityAnalyzerTool.Input(
            dependent_series_id="BDDK_MONTHLY:tuketici_kredileri:tuketici_kredileri_konut",
            independent_series_id="EVDS:TP.GENENDEKS.T1",
            dependent_dimension="Toplam",
            method="arc_elasticity",
            start_date="2023-01-01",
            end_date="2024-12-31",
        )
    )

    assert result.success is True
    assert result.elasticity_coefficient is not None
    assert result.classification is not None
    assert result.interpretation is not None
    assert result.chart_url is not None


def test_elasticity_analyzer_series_not_found():
    tool = ElasticityAndSensitivityAnalyzerTool()
    result = tool.run(
        ElasticityAndSensitivityAnalyzerTool.Input(
            dependent_series_id="UNKNOWN_SERIES_AAA",
            independent_series_id="UNKNOWN_SERIES_BBB",
        )
    )
    assert result.success is False
    assert "bulunamadi" in result.error.lower()


def test_elasticity_analyzer_schema_validation():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        # dependent_series_id ve independent_series_id zorunludur
        ElasticityAndSensitivityAnalyzerTool.Input()  # type: ignore
