"""Inline observations and cross-source analysis tests for causality_check."""
from __future__ import annotations

from pathlib import Path
import duckdb
import pytest
from pydantic import ValidationError

import backend.app.tools.causality_check as tool_module
from backend.app.tools.causality_check import CausalityCheckTool

GOLD_PARQUET = Path(__file__).resolve().parents[3] / "data" / "gold" / "gold_periodic_change.parquet"

OBSERVATIONS_A = [
    {"date": "2024-01-01", "value": 100.0},
    {"date": "2024-02-01", "value": 120.0},
    {"date": "2024-03-01", "value": 140.0},
    {"date": "2024-04-01", "value": 160.0},
]

OBSERVATIONS_B = [
    {"date": "2024-01-01", "value": 10.0},
    {"date": "2024-02-01", "value": 12.0},
    {"date": "2024-03-01", "value": 14.0},
    {"date": "2024-04-01", "value": 16.0},
]

OBSERVATIONS_B_MONTH_END = [
    {"date": "2024-01-31", "value": 10.0},
    {"date": "2024-02-29", "value": 12.0},
    {"date": "2024-03-31", "value": 14.0},
    {"date": "2024-04-30", "value": 16.0},
]


@pytest.fixture
def no_lakehouse(monkeypatch):
    """Lakehouse'a her türlü erişimi imkânsız kıl; erişilirse test kırılır."""
    monkeypatch.setattr(tool_module, "GOLD_PARQUET", Path("/nonexistent/lakehouse.parquet"))

    def _forbidden(*args, **kwargs):
        raise AssertionError("inline dalı lakehouse'a (duckdb) erişmemeli")

    monkeypatch.setattr(duckdb, "connect", _forbidden)


def test_causality_validation_errors():
    tool = CausalityCheckTool()

    # Taraf A eksik (ne series_id_a ne observations_a var)
    with pytest.raises(ValidationError):
        tool.Input(series_id_b="EVDS:TP.KTF12")

    # Taraf A her ikisi birden verilmiş
    with pytest.raises(ValidationError):
        tool.Input(
            series_id_a="EVDS:TP.KTF10",
            observations_a=OBSERVATIONS_A,
            series_id_b="EVDS:TP.KTF12",
        )

    # Taraf B eksik (ne series_id_b ne observations_b var)
    with pytest.raises(ValidationError):
        tool.Input(series_id_a="EVDS:TP.KTF10")

    # Taraf B her ikisi birden verilmiş
    with pytest.raises(ValidationError):
        tool.Input(
            series_id_a="EVDS:TP.KTF10",
            series_id_b="EVDS:TP.KTF12",
            observations_b=OBSERVATIONS_B,
        )


def test_causality_both_sides_inline_without_lakehouse(no_lakehouse):
    tool = CausalityCheckTool()
    result = tool.run(
        tool.Input(
            observations_a=OBSERVATIONS_A,
            observations_b=OBSERVATIONS_B,
        )
    )

    assert result.success is True, result.error
    assert result.data_source_a == "inline"
    assert result.data_source_b == "inline"
    assert result.n_observations == 4
    assert result.correlation_coefficient == pytest.approx(1.0)
    assert "korelasyon" in result.interpretation.lower()


def test_causality_month_fallback_matching(no_lakehouse):
    tool = CausalityCheckTool()
    result = tool.run(
        tool.Input(
            observations_a=OBSERVATIONS_A,
            observations_b=OBSERVATIONS_B_MONTH_END,
        )
    )

    assert result.success is True, result.error
    assert result.n_observations == 4
    assert result.correlation_coefficient == pytest.approx(1.0)
    assert any("ay bazında" in w.lower() or "ay bazinda" in w.lower() for w in result.warnings)


def test_causality_inline_dimension_ignored_with_warning(no_lakehouse):
    tool = CausalityCheckTool()
    result = tool.run(
        tool.Input(
            observations_a=OBSERVATIONS_A,
            observations_b=OBSERVATIONS_B,
            dimension_a="Toplam",
            dimension_b="Diger",
        )
    )

    assert result.success is True, result.error
    assert any("a" in w.lower() and "dimension" in w.lower() for w in result.warnings)
    assert any("b" in w.lower() and "dimension" in w.lower() for w in result.warnings)


def test_causality_inline_unsupported_metric_returns_error(no_lakehouse):
    tool = CausalityCheckTool()
    result = tool.run(
        tool.Input(
            observations_a=OBSERVATIONS_A,
            observations_b=OBSERVATIONS_B,
            metric="mom_abs_change",
        )
    )

    assert result.success is False
    assert result.error is not None
    assert "yalnızca 'value' ve 'mom_pct_change'" in result.error


def test_causality_too_few_observations_returns_error(no_lakehouse):
    tool = CausalityCheckTool()
    # Kesismeyen tarihler
    obs_b_non_overlapping = [
        {"date": "2025-01-01", "value": 10.0},
        {"date": "2025-02-01", "value": 12.0},
        {"date": "2025-03-01", "value": 14.0},
    ]
    result = tool.run(
        tool.Input(
            observations_a=OBSERVATIONS_A,
            observations_b=obs_b_non_overlapping,
        )
    )

    assert result.success is False
    assert result.error is not None
    assert "en az iki ortak gozlem gereklidir" in result.error.lower()


def test_causality_zero_variance_returns_error(no_lakehouse):
    tool = CausalityCheckTool()
    obs_constant = [
        {"date": "2024-01-01", "value": 100.0},
        {"date": "2024-02-01", "value": 100.0},
        {"date": "2024-03-01", "value": 100.0},
        {"date": "2024-04-01", "value": 100.0},
    ]
    result = tool.run(
        tool.Input(
            observations_a=obs_constant,
            observations_b=OBSERVATIONS_B,
        )
    )

    assert result.success is False
    assert result.error is not None
    assert "varyansi sifir" in result.error.lower()


def test_causality_start_date_without_end_date_returns_error(no_lakehouse):
    tool = CausalityCheckTool()
    result = tool.run(
        tool.Input(
            observations_a=OBSERVATIONS_A,
            observations_b=OBSERVATIONS_B,
            start_date="2024-01-01",
        )
    )

    assert result.success is False
    assert result.error is not None
    assert "birlikte verilmelidir" in result.error.lower()


@pytest.mark.skipif(not GOLD_PARQUET.exists(), reason="Lakehouse verisi yok.")
def test_causality_one_side_inline_one_side_lakehouse():
    tool = CausalityCheckTool()
    # 2023-01'den 2023-06'ya inline veri
    custom_observations = [
        {"date": "2023-01-01", "value": 10.5},
        {"date": "2023-02-01", "value": 11.0},
        {"date": "2023-03-01", "value": 12.2},
        {"date": "2023-04-01", "value": 13.1},
        {"date": "2023-05-01", "value": 14.0},
        {"date": "2023-06-01", "value": 15.5},
    ]
    result = tool.run(
        tool.Input(
            observations_a=custom_observations,
            series_id_b="EVDS:TP.KTF12",
            start_date="2023-01-01",
            end_date="2023-06-30",
        )
    )

    assert result.success is True, result.error
    assert result.data_source_a == "inline"
    assert result.data_source_b == "lakehouse"
    assert result.n_observations >= 3
    assert result.correlation_coefficient is not None
