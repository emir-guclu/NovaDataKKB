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


def test_risk_concentration_analyzer_inline_items():
    tool = RiskConcentrationAnalyzerTool()
    items = [
        {"entity": "Firma A", "value": 100.0},
        {"entity": "Firma B", "value": 50.0},
        {"entity": "Firma C", "value": 30.0},
        {"entity": "Firma D", "value": 15.0},
        {"entity": "Firma E", "value": 5.0},
    ]
    # Total = 200.0
    # Shares: A: 50%, B: 25%, C: 15%, D: 7.5%, E: 2.5%
    # CR3: 50 + 25 + 15 = 90.0%
    # CR5: 90 + 7.5 + 2.5 = 100.0%
    # HHI: 50^2 + 25^2 + 15^2 + 7.5^2 + 2.5^2 = 2500 + 625 + 225 + 56.25 + 6.25 = 3412.5
    result = tool.run(
        RiskConcentrationAnalyzerTool.Input(
            items=items,
            top_k=5,
        )
    )

    assert result.success is True
    assert result.data_source == "inline"
    assert result.total_risk_amount == 200.0
    assert result.cr3_share_pct == 90.0
    assert result.cr5_share_pct == 100.0
    assert result.hhi_score == 3412.5
    assert result.hhi_level == "Yüksek Yoğunlaşma / Kritik Risk Kümelenmesi"
    assert len(result.top_entities) == 5
    assert result.top_entities[0]["amount"] == 100.0
    assert result.chart_url is not None
    assert result.chart_url.startswith("/static/charts/concentration_")


def test_risk_concentration_analyzer_inline_turkish_keys_and_string_values():
    tool = RiskConcentrationAnalyzerTool()
    items = [
        {"firma": "A Holding", "risk": "450.000"},
        {"firma": "B Grubu", "risk": "300.000 TL"},
        {"firma": "C A.Ş.", "risk": "150.000"},
        {"firma": "D Ltd.", "risk": "70.000"},
        {"firma": "E Ticaret", "risk": "30.000"},
    ]
    # Total = 1000.0
    # Shares: A: 45%, B: 30%, C: 15%, D: 7%, E: 3%
    # CR3: 45 + 30 + 15 = 90.0%
    # HHI: 45^2 + 30^2 + 15^2 + 7^2 + 3^2 = 2025 + 900 + 225 + 49 + 9 = 3208.0
    result = tool.run(
        RiskConcentrationAnalyzerTool.Input(
            items=items,
            top_k=5,
        )
    )

    assert result.success is True
    assert result.data_source == "inline"
    assert result.total_risk_amount == 1000000.0
    assert result.cr3_share_pct == 90.0
    assert result.cr5_share_pct == 100.0
    assert result.hhi_score == 3208.0
    assert result.hhi_level == "Yüksek Yoğunlaşma / Kritik Risk Kümelenmesi"
    assert len(result.top_entities) == 5
    assert result.chart_url is not None


def test_risk_concentration_analyzer_inline_invalid_data():
    tool = RiskConcentrationAnalyzerTool()

    # Boş liste
    result_empty = tool.run(RiskConcentrationAnalyzerTool.Input(items=[]))
    assert result_empty.success is False
    assert "en az 2" in result_empty.error.lower()

    # Tek varlık
    result_single = tool.run(RiskConcentrationAnalyzerTool.Input(items=[{"entity": "Tek Firma", "value": 100}]))
    assert result_single.success is False
    assert "en az 2" in result_single.error.lower()

    # Negatif / sıfır değerler
    result_zero = tool.run(RiskConcentrationAnalyzerTool.Input(items=[
        {"entity": "A", "value": 0},
        {"entity": "B", "value": -50}
    ]))
    assert result_zero.success is False

    # Kısmi geçersiz satırlar (uyarı üretilmeli, kalan geçerli olanlar hesaplanmalı)
    result_partial = tool.run(RiskConcentrationAnalyzerTool.Input(items=[
        {"entity": "A", "value": 100},
        {"entity": "", "value": 50},  # geçersiz entity
        {"entity": "B", "value": "geçersiz_sayı"},  # geçersiz sayı
        {"entity": "C", "value": 200},
    ]))
    assert result_partial.success is True
    assert result_partial.data_source == "inline"
    assert len(result_partial.warnings) >= 1
    assert result_partial.total_risk_amount == 300.0


def test_risk_concentration_analyzer_inline_duplicates_and_optional_table_name():
    tool = RiskConcentrationAnalyzerTool()
    items = [
        {"entity": "Firma A", "value": 50.0},
        {"entity": "Firma A", "value": 50.0},
        {"entity": "Firma B", "value": 100.0},
    ]
    result = tool.run(
        RiskConcentrationAnalyzerTool.Input(
            table_name=None,
            items=items,
            date="2025-12-31",
            top_k=2,
        )
    )
    assert result.success is True
    assert result.data_source == "inline"
    assert result.total_risk_amount == 200.0
    assert result.date_analyzed == "2025-12-31"
    assert len(result.top_entities) == 2
    # Both have 100.0
    assert result.top_entities[0]["amount"] == 100.0
    assert result.top_entities[1]["amount"] == 100.0


