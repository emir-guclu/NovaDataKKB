from pathlib import Path
import pytest

from backend.app.services.chart_generator import (
    generate_deflator_chart,
    generate_elasticity_chart,
    generate_concentration_chart,
    generate_cycle_chart,
    CHARTS_DIR,
)


def test_generate_deflator_chart_creates_file():
    dates = ["2023-01", "2023-02", "2023-03", "2023-04"]
    nominal = [100.0, 110.0, 120.0, 130.0]
    real = [100.0, 105.0, 108.0, 112.0]

    url = generate_deflator_chart(dates, nominal, real, series_name="Krediler", unit="Milyar TL")
    assert url.startswith("/static/charts/deflator_")
    assert url.endswith(".png")

    file_name = url.replace("/static/charts/", "")
    file_path = CHARTS_DIR / file_name
    assert file_path.exists()
    assert file_path.stat().st_size > 1000


def test_generate_elasticity_chart_creates_file():
    x = [10.0, 15.0, 20.0, 25.0, 30.0, 35.0]
    y = [5.0, 4.2, 3.8, 3.1, 2.5, 1.9]

    url = generate_elasticity_chart(
        x_values=x,
        y_values=y,
        x_label="Politika Faizi (%)",
        y_label="Kredi Talebi (Milyon TL)",
        beta=-1.45,
        r_squared=0.88,
    )
    assert url.startswith("/static/charts/elasticity_")
    assert url.endswith(".png")

    file_name = url.replace("/static/charts/", "")
    file_path = CHARTS_DIR / file_name
    assert file_path.exists()
    assert file_path.stat().st_size > 1000


def test_generate_concentration_chart_creates_file():
    labels = ["İstanbul", "Ankara", "İzmir", "Bursa", "Antalya", "Adana"]
    values = [500.0, 200.0, 150.0, 80.0, 40.0, 30.0]

    url = generate_concentration_chart(
        labels=labels,
        values=values,
        cr3_pct=85.0,
        cr5_pct=97.0,
        hhi_score=3120.5,
        dimension_name="İller",
    )
    assert url.startswith("/static/charts/concentration_")
    assert url.endswith(".png")

    file_name = url.replace("/static/charts/", "")
    file_path = CHARTS_DIR / file_name
    assert file_path.exists()
    assert file_path.stat().st_size > 1000


def test_generate_cycle_chart_creates_file():
    dates = [f"2023-{i:02d}" for i in range(1, 13)]
    values = [10, 12, 15, 18, 16, 14, 11, 9, 8, 12, 17, 20]
    peaks = [3, 11]
    troughs = [8]

    url = generate_cycle_chart(
        dates=dates,
        values=values,
        peaks_indices=peaks,
        troughs_indices=troughs,
        title="Konut Kredisi Döngüsü",
    )
    assert url.startswith("/static/charts/cycle_")
    assert url.endswith(".png")

    file_name = url.replace("/static/charts/", "")
    file_path = CHARTS_DIR / file_name
    assert file_path.exists()
    assert file_path.stat().st_size > 1000
