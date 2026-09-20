import pytest
from backend.app.tools.anomaly_detection import AnomalyDetectionTool


def test_masking_effect_robust_detects_both_spikes_where_zscore_masks():
    """
    Masking Effect Acceptance Criterion:
    A series with a stable baseline and two shocks (one massive shock and one notable shock).
    Classical z-score: Standard deviation is inflated by the massive shock, masking the second shock (z < 2.0).
    Robust z-score: Median and MAD are resistant to extreme outliers, correctly detecting both shocks (z >= 2.0).
    """
    tool = AnomalyDetectionTool()

    # 18 baseline values around 100.0, one massive shock (500.0), one secondary shock (250.0)
    baseline = [100.0 + (i % 3 - 1) * 0.5 for i in range(18)]  # 99.5 to 100.5
    series_values = baseline + [500.0, 250.0]
    observations = [{"date": f"2024-01-{i + 1:02d}", "value": v} for i, v in enumerate(series_values)]

    # 1. Classical z-score
    result_zscore = tool.run(
        tool.Input(
            observations=observations,
            metric="value",
            method="zscore",
            z_threshold=2.0,
        )
    )
    assert result_zscore.success is True
    assert result_zscore.method == "zscore"
    assert result_zscore.mean is not None
    assert result_zscore.stddev is not None
    # Classical z-score should only detect 1 anomaly (500.0) because stddev is inflated to ~90+, masking 250.0
    detected_dates_zscore = [a["date"] for a in result_zscore.anomalies]
    assert len(detected_dates_zscore) == 1
    assert detected_dates_zscore == ["2024-01-19"]

    # 2. Robust z-score (default)
    result_robust = tool.run(
        tool.Input(
            observations=observations,
            metric="value",
            method="robust",
            z_threshold=2.0,
        )
    )
    assert result_robust.success is True
    assert result_robust.method == "robust"
    assert result_robust.median is not None
    assert result_robust.mad is not None
    # Robust z-score should detect both 500.0 and 250.0
    detected_dates_robust = [a["date"] for a in result_robust.anomalies]
    assert len(detected_dates_robust) == 2
    assert "2024-01-19" in detected_dates_robust
    assert "2024-01-20" in detected_dates_robust


def test_default_method_is_robust():
    tool = AnomalyDetectionTool()
    observations = [
        {"date": f"2024-01-{i + 1:02d}", "value": 10.0 if i != 5 else 100.0}
        for i in range(15)
    ]
    inp = tool.Input(observations=observations, metric="value")
    assert inp.method == "robust"

    result = tool.run(inp)
    assert result.success is True
    assert result.method == "robust"
    assert result.median == pytest.approx(10.0)
    assert result.mad is not None
    assert result.mean is None
    assert result.stddev is None
    assert len(result.anomalies) == 1
    assert result.anomalies[0]["date"] == "2024-01-06"


def test_robust_zero_mad_fallback():
    """When more than 50% of the data is identical, MAD is 0.0. Tool should use 1e-9 fallback without error."""
    tool = AnomalyDetectionTool()
    # 10 identical values (100.0) and one outlier (200.0)
    observations = [{"date": f"2024-01-{i + 1:02d}", "value": 100.0} for i in range(10)]
    observations.append({"date": "2024-01-11", "value": 200.0})

    result = tool.run(tool.Input(observations=observations, metric="value", method="robust"))
    assert result.success is True
    assert result.mad == 0.0
    assert result.median == 100.0
    assert len(result.anomalies) == 1
    assert result.anomalies[0]["date"] == "2024-01-11"
    assert result.anomalies[0]["z_score"] > 2.0
