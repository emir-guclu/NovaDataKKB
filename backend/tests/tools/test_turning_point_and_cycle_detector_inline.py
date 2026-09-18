"""Inline observations tests for turning_point_and_cycle_detector."""
from __future__ import annotations

import duckdb
import pytest
from pydantic import ValidationError

import backend.app.tools.turning_point_and_cycle_detector as tool_module
from backend.app.tools.turning_point_and_cycle_detector import TurningPointAndCycleDetectorTool

SERIES = [100, 108, 117, 125, 118, 108, 99, 92, 100, 111, 121, 130, 122, 112, 103]
OBSERVATIONS = [
    {"date": f"{2023 + i // 12}-{i % 12 + 1:02d}-01", "value": v} for i, v in enumerate(SERIES)
]


@pytest.fixture
def no_lakehouse(monkeypatch):
    """Lakehouse'a her türlü erişimi imkânsız kıl; erişilirse test kırılır."""
    monkeypatch.setattr(tool_module, "ALIGNED_PARQUET", tool_module.Path("/nonexistent/lakehouse.parquet"))

    def _forbidden(*args, **kwargs):
        raise AssertionError("inline dalı lakehouse'a (duckdb) erişmemeli")

    monkeypatch.setattr(duckdb, "connect", _forbidden)


@pytest.fixture(autouse=True)
def _no_chart_file(monkeypatch):
    monkeypatch.setattr(tool_module, "generate_cycle_chart", lambda **kwargs: "/static/charts/cycle_test.png")


def test_inline_observations_find_turning_points_without_lakehouse(no_lakehouse):
    tool = TurningPointAndCycleDetectorTool()
    result = tool.run(tool.Input(observations=OBSERVATIONS, smoothing_window=1, min_cycle_length=4))

    assert result.success is True, result.error
    assert result.data_source == "inline"
    assert result.series_id is None
    assert result.peaks and result.troughs
    assert result.max_drawdown_pct is not None
    assert result.chart_url == "/static/charts/cycle_test.png"


def test_inline_dimension_is_ignored_with_warning(no_lakehouse):
    tool = TurningPointAndCycleDetectorTool()
    result = tool.run(tool.Input(observations=OBSERVATIONS, dimension="Toplam", smoothing_window=1))

    assert result.success is True, result.error
    assert "Satır içi seride dimension kullanılmaz, yok sayıldı." in result.warnings


def test_inline_fewer_than_six_observations_reports_inline_source(no_lakehouse):
    tool = TurningPointAndCycleDetectorTool()
    result = tool.run(tool.Input(observations=OBSERVATIONS[:4]))

    assert result.success is False
    assert result.data_source == "inline"
    assert "en az 6 gözlem" in result.error


def test_series_id_and_observations_together_is_validation_error():
    with pytest.raises(ValidationError):
        TurningPointAndCycleDetectorTool.Input(series_id="X", observations=OBSERVATIONS)


def test_neither_series_id_nor_observations_is_validation_error():
    with pytest.raises(ValidationError):
        TurningPointAndCycleDetectorTool.Input()


def test_lakehouse_branch_reports_error_when_parquet_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(tool_module, "ALIGNED_PARQUET", tmp_path / "yok.parquet")
    result = TurningPointAndCycleDetectorTool().run(TurningPointAndCycleDetectorTool.Input(series_id="X"))
    assert result.success is False
    assert "Aligned parquet bulunamadi" in result.error

