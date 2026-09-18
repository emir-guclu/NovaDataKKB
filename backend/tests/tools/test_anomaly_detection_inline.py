"""Inline observations tests for anomaly_detection."""
from __future__ import annotations

import duckdb
import pytest
from pydantic import ValidationError

import backend.app.tools.anomaly_detection as tool_module
from backend.app.tools.anomaly_detection import AnomalyDetectionTool

SERIES = [100.0, 101.0, 100.5, 99.8, 100.2, 101.2, 100.1, 180.0, 100.4, 99.9, 100.8, 100.3]
OBSERVATIONS = [{"date": f"2024-{i + 1:02d}-01", "value": v} for i, v in enumerate(SERIES)]


@pytest.fixture
def no_lakehouse(monkeypatch):
    """Lakehouse'a her türlü erişimi imkânsız kıl; erişilirse test kırılır."""
    monkeypatch.setattr(tool_module, "GOLD_PARQUET", tool_module.Path("/nonexistent/lakehouse.parquet"))

    def _forbidden(*args, **kwargs):
        raise AssertionError("inline dalı lakehouse'a (duckdb) erişmemeli")

    monkeypatch.setattr(duckdb, "connect", _forbidden)


def test_inline_observations_detect_obvious_outlier_without_lakehouse(no_lakehouse):
    tool = AnomalyDetectionTool()
    result = tool.run(tool.Input(observations=OBSERVATIONS, metric="value", z_threshold=2.0))

    assert result.success is True, result.error
    assert result.data_source == "inline"
    assert result.n_observations == 12
    assert [a["date"] for a in result.anomalies] == ["2024-08-01"]
    assert result.anomalies[0]["direction"] == "high"


def test_inline_default_metric_mom_pct_change_flags_spike(no_lakehouse):
    tool = AnomalyDetectionTool()
    result = tool.run(tool.Input(observations=OBSERVATIONS, z_threshold=2.0))

    assert result.success is True, result.error
    assert result.data_source == "inline"
    assert result.n_observations == 11  # ilk gözlem düşer
    assert result.anomalies[0]["date"] in {"2024-08-01", "2024-09-01"}
    assert any("ardışık gözlemler" in w for w in result.warnings)


def test_inline_dimension_is_ignored_with_warning(no_lakehouse):
    tool = AnomalyDetectionTool()
    result = tool.run(tool.Input(observations=OBSERVATIONS, metric="value", dimension="Toplam"))

    assert result.success is True
    assert result.selected_dimension is None
    assert "Satır içi seride dimension kullanılmaz, yok sayıldı." in result.warnings


def test_inline_unsupported_metric_returns_corrective_error(no_lakehouse):
    tool = AnomalyDetectionTool()
    result = tool.run(tool.Input(observations=OBSERVATIONS, metric="yoy_pct_change"))

    assert result.success is False
    assert result.data_source == "inline"
    assert "yalnızca 'value' ve 'mom_pct_change'" in result.error


def test_series_id_and_observations_together_is_validation_error():
    with pytest.raises(ValidationError):
        AnomalyDetectionTool.Input(series_id="X", observations=OBSERVATIONS)


def test_neither_series_id_nor_observations_is_validation_error():
    with pytest.raises(ValidationError):
        AnomalyDetectionTool.Input()


def test_lakehouse_branch_reports_lakehouse_data_source_on_error(monkeypatch, tmp_path):
    monkeypatch.setattr(tool_module, "GOLD_PARQUET", tmp_path / "yok.parquet")
    result = AnomalyDetectionTool().run(AnomalyDetectionTool.Input(series_id="X"))
    assert result.success is False
    assert "Gold parquet bulunamadi" in result.error

