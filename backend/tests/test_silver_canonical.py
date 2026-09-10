from datetime import date

import pytest
from pydantic import ValidationError

from app.models.silver_canonical import (
    CanonicalObservation,
    CanonicalSeriesMetadata,
)


def test_canonical_observation_accepts_shared_schema():
    obs = CanonicalObservation(
        series_id="TEST:1",
        source="BDDK",
        date=date(2021, 1, 31),
        period_start=date(2021, 1, 1),
        period_end=date(2021, 1, 31),
        value=100.0,
        freq="M",
        unit="milyon TL",
        dims={
            "province": "İstanbul",
            "plate_code": "34",
        },
        source_file="test.csv",
    )

    assert obs.date == obs.period_end
    assert obs.dims["plate_code"] == "34"


def test_date_must_equal_period_end():
    with pytest.raises(ValidationError):
        CanonicalObservation(
            series_id="TEST:1",
            source="EVDS",
            date=date(2021, 1, 1),
            period_start=date(2021, 1, 1),
            period_end=date(2021, 1, 31),
            value=1.0,
            freq="M",
        )


def test_period_start_cannot_be_after_period_end():
    with pytest.raises(ValidationError):
        CanonicalObservation(
            series_id="TEST:1",
            source="EVDS",
            date=date(2021, 1, 31),
            period_start=date(2021, 2, 1),
            period_end=date(2021, 1, 31),
            value=1.0,
            freq="M",
        )


def test_invalid_frequency_rejected():
    with pytest.raises(ValidationError):
        CanonicalObservation(
            series_id="TEST:1",
            source="EVDS",
            date=date(2021, 1, 31),
            period_start=date(2021, 1, 1),
            period_end=date(2021, 1, 31),
            value=1.0,
            freq="MONTHLY",
        )


def test_metadata_defaults_non_cumulative():
    meta = CanonicalSeriesMetadata(
        series_id="EVDS:TEST",
        source="EVDS",
        series_code="TEST",
        series_name="Test Series",
        category="test",
        freq="M",
        unit="%",
    )

    assert meta.accumulation == "none"
    assert meta.is_cumulative is False


def test_ytd_metadata_must_be_cumulative():
    meta = CanonicalSeriesMetadata(
        series_id="BDDK:TEST",
        source="BDDK_MONTHLY",
        series_name="Test YTD Series",
        category="kar_zarar",
        freq="M",
        unit="milyon TL",
        accumulation="ytd",
        is_cumulative=True,
    )

    assert meta.is_cumulative is True


def test_inconsistent_cumulative_metadata_rejected():
    with pytest.raises(ValidationError):
        CanonicalSeriesMetadata(
            series_id="BDDK:TEST",
            source="BDDK_MONTHLY",
            series_name="Bad Series",
            category="kar_zarar",
            freq="M",
            accumulation="ytd",
            is_cumulative=False,
        )
