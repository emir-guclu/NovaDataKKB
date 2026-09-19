"""Tests for lead-lag cross-correlation scan in causality_check."""
from __future__ import annotations

from pathlib import Path
import pytest

from backend.app.tools.causality_check import CausalityCheckTool

GOLD_PARQUET = Path(__file__).resolve().parents[3] / "data" / "gold" / "gold_periodic_change.parquet"

DATES_14 = [
    f"2024-{m:02d}-01" for m in range(1, 13)
] + ["2025-01-01", "2025-02-01"]

SERIES_FLUCTUATING = [
    10.0, 25.0, 12.0, 30.0, 18.0, 40.0, 22.0, 50.0, 35.0, 60.0, 45.0, 70.0, 55.0, 80.0
]


def test_causality_synthetic_lag_positive():
    """Taraf A, Taraf B'ye 3 dönem öncülük ediyor: b[t] = a[t-3]. Beklenen optimal_lag = 3."""
    tool = CausalityCheckTool()

    # b[t] = a[t-3] for t >= 3; initial 3 points are fillers
    b_values = [0.0, 5.0, -2.0] + SERIES_FLUCTUATING[:11]

    obs_a = [{"date": d, "value": v} for d, v in zip(DATES_14, SERIES_FLUCTUATING)]
    obs_b = [{"date": d, "value": v} for d, v in zip(DATES_14, b_values)]

    result = tool.run(
        tool.Input(
            observations_a=obs_a,
            observations_b=obs_b,
            max_lag=5,
        )
    )

    assert result.success is True, result.error
    assert result.optimal_lag == 3
    assert result.optimal_correlation == pytest.approx(1.0, abs=1e-3)
    assert 3 in result.lag_correlations
    assert result.lag_correlations[3] == pytest.approx(1.0, abs=1e-3)
    assert result.lead_lag_interpretation is not None
    assert "3" in result.lead_lag_interpretation
    assert "önden" in result.lead_lag_interpretation or "öncülük" in result.lead_lag_interpretation or "gecikmeyle" in result.lead_lag_interpretation


def test_causality_synthetic_lag_negative():
    """Taraf B, Taraf A'ya 2 dönem öncülük ediyor: a[t] = b[t-2]. Beklenen optimal_lag = -2."""
    tool = CausalityCheckTool()

    # a[t] = b[t-2] for t >= 2; initial 2 points are fillers
    a_values = [0.0, -5.0] + SERIES_FLUCTUATING[:12]

    obs_a = [{"date": d, "value": v} for d, v in zip(DATES_14, a_values)]
    obs_b = [{"date": d, "value": v} for d, v in zip(DATES_14, SERIES_FLUCTUATING)]

    result = tool.run(
        tool.Input(
            observations_a=obs_a,
            observations_b=obs_b,
            max_lag=4,
        )
    )

    assert result.success is True, result.error
    assert result.optimal_lag == -2
    assert result.optimal_correlation == pytest.approx(1.0, abs=1e-3)
    assert -2 in result.lag_correlations
    assert result.lag_correlations[-2] == pytest.approx(1.0, abs=1e-3)
    assert result.lead_lag_interpretation is not None
    assert "2" in result.lead_lag_interpretation


def test_causality_synthetic_lag_simultaneous():
    """Eşzamanlı seriler (b[t] = 2*a[t] + 5). Beklenen optimal_lag = 0."""
    tool = CausalityCheckTool()

    b_values = [2.0 * v + 5.0 for v in SERIES_FLUCTUATING]

    obs_a = [{"date": d, "value": v} for d, v in zip(DATES_14, SERIES_FLUCTUATING)]
    obs_b = [{"date": d, "value": v} for d, v in zip(DATES_14, b_values)]

    result = tool.run(
        tool.Input(
            observations_a=obs_a,
            observations_b=obs_b,
            max_lag=6,
        )
    )

    assert result.success is True, result.error
    assert result.optimal_lag == 0
    assert result.optimal_correlation == pytest.approx(1.0, abs=1e-3)
    assert result.correlation_coefficient == pytest.approx(1.0, abs=1e-3)
    assert result.lead_lag_interpretation is not None
    assert "eşzamanlı" in result.lead_lag_interpretation.lower() or "lag = 0" in result.lead_lag_interpretation


def test_causality_max_lag_zero_disables_lag_scan():
    """max_lag=0 verildiğinde gecikme taraması devre dışı bırakılmalıdır."""
    tool = CausalityCheckTool()

    obs_a = [{"date": d, "value": v} for d, v in zip(DATES_14, SERIES_FLUCTUATING)]
    obs_b = [{"date": d, "value": 2.0 * v} for d, v in zip(DATES_14, SERIES_FLUCTUATING)]

    result = tool.run(
        tool.Input(
            observations_a=obs_a,
            observations_b=obs_b,
            max_lag=0,
        )
    )

    assert result.success is True, result.error
    assert result.correlation_coefficient == pytest.approx(1.0, abs=1e-3)
    assert result.optimal_lag is None
    assert result.optimal_correlation is None
    assert result.lag_correlations == {}
    assert result.lead_lag_interpretation is None


def test_causality_lead_lag_insufficient_observations():
    """Ortak gözlem sayısı < 4 olduğunda lag taraması yapılmamalı, eşzamanlı korelasyon hesaplanmalıdır."""
    tool = CausalityCheckTool()

    obs_a = [
        {"date": "2024-01-01", "value": 10.0},
        {"date": "2024-02-01", "value": 20.0},
        {"date": "2024-03-01", "value": 15.0},
    ]
    obs_b = [
        {"date": "2024-01-01", "value": 100.0},
        {"date": "2024-02-01", "value": 200.0},
        {"date": "2024-03-01", "value": 150.0},
    ]

    result = tool.run(
        tool.Input(
            observations_a=obs_a,
            observations_b=obs_b,
            max_lag=2,
        )
    )

    assert result.success is True, result.error
    assert result.n_observations == 3
    assert result.correlation_coefficient == pytest.approx(1.0, abs=1e-3)
    assert result.optimal_lag is None
    assert result.lag_correlations == {}


@pytest.mark.skipif(not GOLD_PARQUET.exists(), reason="Lakehouse verisi yok.")
def test_causality_lead_lag_with_real_gold_data():
    """Gerçek Lakehouse verileriyle (BDDK Konut Kredisi & EVDS Konut Faiz Oranı) gecikmeli korelasyon testi."""
    tool = CausalityCheckTool()

    result = tool.run(
        tool.Input(
            series_id_a="BDDK_MONTHLY:tuketici_kredileri:tuketici_kredileri_konut",
            series_id_b="EVDS:TP.KTF12",
            dimension_a="Toplam",
            start_date="2023-01-01",
            end_date="2026-06-30",
            max_lag=6,
        )
    )

    assert result.success is True, result.error
    assert result.correlation_coefficient is not None
    assert result.optimal_lag is not None
    assert result.optimal_correlation is not None
    assert isinstance(result.lag_correlations, dict)
    assert len(result.lag_correlations) >= 7  # -6..+6
    assert 0 in result.lag_correlations
    assert result.lag_correlations[0] == pytest.approx(result.correlation_coefficient, abs=1e-4)
    assert result.lead_lag_interpretation is not None
