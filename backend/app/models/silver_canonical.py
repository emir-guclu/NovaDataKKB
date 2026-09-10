"""Cross-source canonical Silver contract.

Used after source-specific Silver processing and before alignment / Gold.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


VALID_FREQS = {"D", "W", "M", "Q", "Y"}
VALID_ACCUMULATIONS = {"none", "ytd", "since_start"}


class CanonicalObservation(BaseModel):
    """Canonical cross-source Silver observation."""

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
    )

    series_id: str
    source: str
    date: date
    period_start: date
    period_end: date
    value: float | None = None
    freq: str
    unit: str | None = None
    dims: dict[str, Any] = Field(default_factory=dict)
    source_file: str | None = None

    @field_validator("freq")
    @classmethod
    def validate_freq(cls, value: str) -> str:
        if value not in VALID_FREQS:
            raise ValueError(
                f"Unsupported canonical frequency: {value!r}"
            )
        return value

    @model_validator(mode="after")
    def validate_period(self) -> "CanonicalObservation":
        if self.period_start > self.period_end:
            raise ValueError(
                "period_start cannot be after period_end"
            )

        if self.date != self.period_end:
            raise ValueError(
                "Canonical observation date must equal period_end"
            )

        return self


class CanonicalSeriesMetadata(BaseModel):
    """Canonical cross-source series metadata."""

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
    )

    series_id: str
    source: str
    series_code: str | None = None
    series_name: str
    category: str
    freq: str
    unit: str | None = None
    description: str | None = None
    tags: list[str] = Field(default_factory=list)
    accumulation: str = "none"
    is_cumulative: bool = False

    @field_validator("freq")
    @classmethod
    def validate_freq(cls, value: str) -> str:
        if value not in VALID_FREQS:
            raise ValueError(
                f"Unsupported canonical frequency: {value!r}"
            )
        return value

    @field_validator("accumulation")
    @classmethod
    def validate_accumulation(cls, value: str) -> str:
        if value not in VALID_ACCUMULATIONS:
            raise ValueError(
                f"Unsupported accumulation type: {value!r}"
            )
        return value

    @model_validator(mode="after")
    def validate_cumulative_semantics(
        self,
    ) -> "CanonicalSeriesMetadata":
        expected = self.accumulation != "none"

        if self.is_cumulative != expected:
            raise ValueError(
                "is_cumulative must match accumulation semantics"
            )

        return self
