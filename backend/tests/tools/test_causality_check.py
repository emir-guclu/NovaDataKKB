import pytest
from pathlib import Path

GOLD_PARQUET = Path(__file__).resolve().parents[3] / "data" / "gold" / "gold_periodic_change.parquet"
pytestmark = pytest.mark.skipif(
    not GOLD_PARQUET.exists(),
    reason="Lakehouse verisi yok (data/gold). SETUP.md'deki pipeline ile üretilir."
)

from pydantic import ValidationError

from backend.app.tools.causality_check import CausalityCheckTool


HOUSING_CREDIT_VOLUME = "BDDK_MONTHLY:tuketici_kredileri:tuketici_kredileri_konut"
HOUSING_CREDIT_RATE = "EVDS:TP.KTF12"


def test_causality_check_success_with_real_gold_data():
    tool = CausalityCheckTool()
    result = tool.run(
        tool.Input(
            series_id_a=HOUSING_CREDIT_VOLUME,
            series_id_b=HOUSING_CREDIT_RATE,
            dimension_a="Toplam",
            start_date="2023-01-01",
            end_date="2026-06-30",
        )
    )

    assert result.success is True
    assert result.error is None
    assert result.metric == "value"
    # TP.KTF12 currently overlaps with the housing-credit volume series
    # for 13 monthly observations in the requested window.
    assert result.n_observations == 13
    assert result.correlation_coefficient == pytest.approx(-0.5720389636140677)
    assert "korelasyon" in result.interpretation.lower()
    assert "nedensellik" in result.interpretation.lower()
    assert "nedensellik ispatı değildir" in result.caveat
    assert "üçüncü faktör" in result.caveat


def test_causality_check_missing_series_returns_structured_error():
    tool = CausalityCheckTool()
    result = tool.run(
        tool.Input(
            series_id_a="SERIES_THAT_DOES_NOT_EXIST",
            series_id_b=HOUSING_CREDIT_RATE,
            start_date="2023-01-01",
            end_date="2026-06-30",
        )
    )

    assert result.success is False
    assert result.error is not None
    assert "Seri bulunamadi" in result.error


def test_causality_check_validation_error():
    tool = CausalityCheckTool()

    with pytest.raises(ValidationError):
        tool.Input(series_id_a=HOUSING_CREDIT_VOLUME)
