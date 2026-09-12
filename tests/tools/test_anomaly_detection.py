import pytest
from pydantic import ValidationError

from backend.app.tools.anomaly_detection import AnomalyDetectionTool


REAL_SERIES = "BDDK_MONTHLY:tuketici_kredileri:tuketici_kredileri_konut"


def test_anomaly_detection_success_with_real_gold_data():
    tool = AnomalyDetectionTool()
    result = tool.run(
        tool.Input(
            series_id=REAL_SERIES,
            dimension="Toplam",
            metric="mom_pct_change",
            z_threshold=2.0,
        )
    )

    assert result.success is True
    assert result.error is None
    assert result.metric == "mom_pct_change"
    assert result.selected_dimension == "Toplam"
    assert result.n_observations == 65
    assert len(result.anomalies) == 3
    assert result.anomalies[0]["date"].startswith("2023-03-31")
    assert result.anomalies[0]["value"] == pytest.approx(0.06493989124712915)
    assert result.anomalies[0]["z_score"] == pytest.approx(3.148910785701634)
    assert result.anomalies[0]["direction"] == "high"


def test_anomaly_detection_missing_series_returns_structured_error():
    tool = AnomalyDetectionTool()
    result = tool.run(
        tool.Input(
            series_id="SERIES_THAT_DOES_NOT_EXIST",
            metric="mom_pct_change",
        )
    )

    assert result.success is False
    assert result.error is not None
    assert "Seri bulunamadi" in result.error


def test_anomaly_detection_rejects_unknown_metric():
    tool = AnomalyDetectionTool()
    result = tool.run(
        tool.Input(
            series_id=REAL_SERIES,
            dimension="Toplam",
            metric="not_a_metric",
        )
    )

    assert result.success is False
    assert result.error is not None
    assert "Metrik desteklenmiyor" in result.error


def test_anomaly_detection_validation_error():
    tool = AnomalyDetectionTool()

    with pytest.raises(ValidationError):
        tool.Input()
