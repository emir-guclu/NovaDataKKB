"""Inline observations tests for change_detection."""
from __future__ import annotations

import duckdb
import pytest
from pydantic import ValidationError

import backend.app.tools.change_detection as tool_module
from backend.app.tools.change_detection import ChangeDetectionTool

OBSERVATIONS = [
    {"date": "2024-01-01", "value": 100},
    {"date": "2024-02-01", "value": 110},
    {"date": "2024-03-01", "value": "99"},
]


@pytest.fixture
def no_lakehouse(monkeypatch):
    """Lakehouse'a her türlü erişimi imkânsız kıl; erişilirse test kırılır."""
    monkeypatch.setattr(tool_module, "GOLD_PARQUET", tool_module.Path("/nonexistent/lakehouse.parquet"))

    def _forbidden(*args, **kwargs):
        raise AssertionError("inline dalı lakehouse'a (duckdb) erişmemeli")

    monkeypatch.setattr(duckdb, "connect", _forbidden)


def test_inline_without_dates_returns_latest_observation_without_lakehouse(no_lakehouse):
    tool = ChangeDetectionTool()
    result = tool.run(tool.Input(observations=OBSERVATIONS))

    assert result.success is True, result.error
    assert result.data_source == "inline"
    assert result.rows == [{"date": "2024-03-01", "value": 99.0, "mom_pct_change": pytest.approx(-10.0)}]


def test_inline_with_date_range_returns_all_rows_with_changes(no_lakehouse):
    tool = ChangeDetectionTool()
    result = tool.run(tool.Input(observations=OBSERVATIONS, start_date="2024-01-01", end_date="2024-03-01"))

    assert result.success is True, result.error
    assert [r["date"] for r in result.rows] == ["2024-01-01", "2024-02-01", "2024-03-01"]
    assert result.rows[0]["mom_pct_change"] is None
    assert result.rows[1]["mom_pct_change"] == pytest.approx(10.0)


def test_inline_dimension_is_ignored_with_warning(no_lakehouse):
    tool = ChangeDetectionTool()
    result = tool.run(tool.Input(observations=OBSERVATIONS, dimension="Toplam"))

    assert result.success is True
    assert "Satır içi seride dimension kullanılmaz, yok sayıldı." in result.warnings


def test_inline_too_few_observations_returns_corrective_error(no_lakehouse):
    tool = ChangeDetectionTool()
    result = tool.run(tool.Input(observations=OBSERVATIONS[:2]))

    assert result.success is False
    assert result.data_source == "inline"
    assert "en az 3" in result.error


def test_series_id_and_observations_together_is_validation_error():
    with pytest.raises(ValidationError):
        ChangeDetectionTool.Input(series_id="X", observations=OBSERVATIONS)


def test_neither_series_id_nor_observations_is_validation_error():
    with pytest.raises(ValidationError):
        ChangeDetectionTool.Input()


def test_lakehouse_branch_reports_error_when_parquet_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(tool_module, "GOLD_PARQUET", tmp_path / "yok.parquet")
    result = ChangeDetectionTool().run(ChangeDetectionTool.Input(series_id="X"))
    assert result.success is False
    assert "Gold parquet bulunamadi" in result.error

