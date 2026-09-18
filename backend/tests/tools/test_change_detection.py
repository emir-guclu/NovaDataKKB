import pytest
from pathlib import Path

GOLD_PARQUET = Path(__file__).resolve().parents[3] / "data" / "gold" / "gold_periodic_change.parquet"
pytestmark = pytest.mark.skipif(
    not GOLD_PARQUET.exists(),
    reason="Lakehouse verisi yok (data/gold). SETUP.md'deki pipeline ile üretilir."
)

from pydantic import ValidationError

from backend.app.tools.change_detection import ChangeDetectionTool


REAL_SERIES = "BDDK_MONTHLY:tuketici_kredileri:tuketici_kredileri_konut"


def test_change_detection_success_with_real_gold_data():
    tool = ChangeDetectionTool()
    params = tool.Input(
        series_id=REAL_SERIES,
        dimension="Toplam",
    )

    result = tool.run(params)

    assert result.success is True
    assert result.error is None
    assert result.selected_dimension == "Toplam"
    assert len(result.rows) == 1

    row = result.rows[0]
    assert str(row["date"]).startswith("2026-06-30")
    assert row["value"] == pytest.approx(801437.882)
    assert row["mom_pct_change"] == pytest.approx(0.023654728971577693)
    assert row["yoy_pct_change"] == pytest.approx(0.3740547318046179)


def test_change_detection_missing_series_returns_structured_error():
    tool = ChangeDetectionTool()
    params = tool.Input(series_id="SERIES_THAT_DOES_NOT_EXIST")

    result = tool.run(params)

    assert result.success is False
    assert result.error is not None
    assert "Seri bulunamadi" in result.error


def test_change_detection_invalid_dimension_returns_structured_error():
    tool = ChangeDetectionTool()
    params = tool.Input(
        series_id=REAL_SERIES,
        dimension="INVALID_DIMENSION",
    )

    result = tool.run(params)

    assert result.success is False
    assert result.error is not None
    assert "Dimension bulunamadi" in result.error


def test_change_detection_requires_date_pair():
    tool = ChangeDetectionTool()
    params = tool.Input(
        series_id=REAL_SERIES,
        start_date="2026-01-01",
    )

    result = tool.run(params)

    assert result.success is False
    assert "birlikte verilmelidir" in result.error


def test_change_detection_validation_error():
    tool = ChangeDetectionTool()

    with pytest.raises(ValidationError):
        tool.Input()
