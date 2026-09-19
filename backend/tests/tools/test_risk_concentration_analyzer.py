import pytest
from backend.app.tools.risk_concentration_analyzer import RiskConcentrationAnalyzerTool


def test_risk_concentration_analyzer_finturk():
    tool = RiskConcentrationAnalyzerTool()
    result = tool.run(
        RiskConcentrationAnalyzerTool.Input(
            table_name="gold_finturk_province_credit_quality",
            dimension_column="province",
            metric_column="nonperforming_receivables",
            top_k=5,
        )
    )

    assert result.success is True
    assert result.metric_unit == "bin TL"
    assert result.cr3_share_pct is not None
    assert result.cr5_share_pct is not None
    assert result.hhi_score is not None
    assert result.hhi_level is not None
    assert len(result.top_entities) == 5
    assert result.chart_url is not None
    assert result.chart_url.startswith("/static/charts/concentration_")


def test_risk_concentration_analyzer_table_not_found():
    tool = RiskConcentrationAnalyzerTool()
    result = tool.run(
        RiskConcentrationAnalyzerTool.Input(
            table_name="non_existent_table_123",
            dimension_column="col1",
            metric_column="col2",
        )
    )
    assert result.success is False
    assert "bulunamadi" in result.error.lower()


def test_risk_concentration_analyzer_schema_validation():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        # top_k 1 ile 50 arasında olmalıdır, 0 verildiğinde ValidationError fırlatır
        RiskConcentrationAnalyzerTool.Input(top_k=0)
