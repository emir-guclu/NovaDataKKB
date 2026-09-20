import pytest
from pydantic import ValidationError

from backend.app.tools.elasticity_and_sensitivity_analyzer import ElasticityAndSensitivityAnalyzerTool


def test_elasticity_validation_errors():
    # 1. Hiçbir parametre verilmediğinde (her iki taraf da eksik)
    with pytest.raises(ValidationError) as exc_info:
        ElasticityAndSensitivityAnalyzerTool.Input()
    err_str = str(exc_info.value)
    assert "dependent" in err_str.lower() or "bağımlı" in err_str.lower()

    # 2. Bağımlı taraf için hem series_id hem observations verildiğinde
    with pytest.raises(ValidationError) as exc_info:
        ElasticityAndSensitivityAnalyzerTool.Input(
            dependent_series_id="TEST:DEP",
            observations_dependent=[{"date": "2024-01-01", "value": 10.0}],
            independent_series_id="TEST:INDEP",
        )
    assert "dependent" in str(exc_info.value).lower() or "bağımlı" in str(exc_info.value).lower()

    # 3. Bağımsız taraf için hem series_id hem observations verildiğinde
    with pytest.raises(ValidationError) as exc_info:
        ElasticityAndSensitivityAnalyzerTool.Input(
            dependent_series_id="TEST:DEP",
            independent_series_id="TEST:INDEP",
            observations_independent=[{"date": "2024-01-01", "value": 10.0}],
        )
    assert "independent" in str(exc_info.value).lower() or "bağımsız" in str(exc_info.value).lower()


def test_elasticity_both_sides_inline_without_lakehouse():
    tool = ElasticityAndSensitivityAnalyzerTool()

    # X: Fiyat/Faiz gibi bağımsız değişken (100, 110, 120, 130, 140, 150)
    # Y: Talep gibi bağımlı değişken (200, 180, 160, 145, 130, 120)
    obs_x = [
        {"date": f"2024-0{i}-01", "value": 100.0 + (i - 1) * 10.0}
        for i in range(1, 7)
    ]
    obs_y = [
        {"date": "2024-01-01", "value": 200.0},
        {"date": "2024-02-01", "value": 180.0},
        {"date": "2024-03-01", "value": 160.0},
        {"date": "2024-04-01", "value": 145.0},
        {"date": "2024-05-01", "value": 130.0},
        {"date": "2024-06-01", "value": 120.0},
    ]

    result = tool.run(
        ElasticityAndSensitivityAnalyzerTool.Input(
            observations_dependent=obs_y,
            observations_independent=obs_x,
            method="log_log_regression",
        )
    )

    assert result.success is True
    assert result.data_source_dependent == "inline"
    assert result.data_source_independent == "inline"
    assert result.elasticity_coefficient is not None
    assert result.elasticity_coefficient < 0  # Talep azaldığı için negatif esneklik
    assert result.r_squared is not None
    assert result.r_squared > 0.8
    assert result.sample_size == 6
    assert result.chart_url is not None
    assert result.chart_url.startswith("/static/charts/elasticity_")


def test_elasticity_one_side_inline_one_side_lakehouse():
    tool = ElasticityAndSensitivityAnalyzerTool()

    # Dışarıdan gelen veri (örn. Borsa Altın hacmi veya özel gösterge)
    # 2023-01-01 ile 2023-12-01 arası aylık gözlemler
    obs_dep = [
        {"date": f"2023-{m:02d}-01", "value": 1000.0 + m * 50.0}
        for m in range(1, 13)
    ]

    result = tool.run(
        ElasticityAndSensitivityAnalyzerTool.Input(
            observations_dependent=obs_dep,
            independent_series_id="EVDS:TP.GENENDEKS.T1",
            method="log_log_regression",
            start_date="2023-01-01",
            end_date="2023-12-31",
        )
    )

    assert result.success is True
    assert result.data_source_dependent == "inline"
    assert result.data_source_independent == "lakehouse"
    assert result.elasticity_coefficient is not None
    assert result.sample_size >= 3
    assert result.chart_url is not None


def test_elasticity_month_fallback_matching():
    tool = ElasticityAndSensitivityAnalyzerTool()

    # Biri ayın 1'i (YYYY-MM-01), diğeri ayın sonu (YYYY-MM-28/30/31)
    obs_dep = [
        {"date": "2024-01-01", "value": 100.0},
        {"date": "2024-02-01", "value": 110.0},
        {"date": "2024-03-01", "value": 125.0},
        {"date": "2024-04-01", "value": 140.0},
    ]
    obs_indep = [
        {"date": "2024-01-31", "value": 50.0},
        {"date": "2024-02-29", "value": 55.0},
        {"date": "2024-03-31", "value": 60.0},
        {"date": "2024-04-30", "value": 70.0},
    ]

    result = tool.run(
        ElasticityAndSensitivityAnalyzerTool.Input(
            observations_dependent=obs_dep,
            observations_independent=obs_indep,
        )
    )

    assert result.success is True
    assert result.sample_size == 4
    assert result.elasticity_coefficient is not None


def test_elasticity_arc_elasticity_inline():
    tool = ElasticityAndSensitivityAnalyzerTool()

    obs_dep = [
        {"date": "2024-01-01", "value": 100.0},
        {"date": "2024-02-01", "value": 120.0},
        {"date": "2024-03-01", "value": 150.0},
    ]
    obs_indep = [
        {"date": "2024-01-01", "value": 50.0},
        {"date": "2024-02-01", "value": 60.0},
        {"date": "2024-03-01", "value": 75.0},
    ]

    result = tool.run(
        ElasticityAndSensitivityAnalyzerTool.Input(
            observations_dependent=obs_dep,
            observations_independent=obs_indep,
            method="arc_elasticity",
        )
    )

    assert result.success is True
    assert result.method == "arc_elasticity"
    assert result.elasticity_coefficient is not None


def test_elasticity_dimension_ignored_warning():
    tool = ElasticityAndSensitivityAnalyzerTool()

    obs_dep = [
        {"date": "2024-01-01", "value": 100.0},
        {"date": "2024-02-01", "value": 120.0},
        {"date": "2024-03-01", "value": 150.0},
    ]
    obs_indep = [
        {"date": "2024-01-01", "value": 50.0},
        {"date": "2024-02-01", "value": 60.0},
        {"date": "2024-03-01", "value": 75.0},
    ]

    result = tool.run(
        ElasticityAndSensitivityAnalyzerTool.Input(
            observations_dependent=obs_dep,
            dependent_dimension="Toplam",
            observations_independent=obs_indep,
            independent_dimension="AltKategori",
        )
    )

    assert result.success is True
    assert any("dimension" in w.lower() for w in result.warnings)
