"""Cross-source canonical Silver contract.

Used after source-specific Silver processing and before alignment / Gold.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


VALID_FREQS = {"D", "W", "M", "Q", "Y"}
VALID_ACCUMULATIONS = {"none", "ytd", "since_start"}
VALID_NATURES = {"stock", "flow", "rate", "price", "unclassified"}
VALID_ALIGNMENT_OVERRIDES = {"last", "sum", "mean"}


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

    @field_validator("dims", mode="before")
    @classmethod
    def validate_dims(cls, value: Any) -> dict[str, Any]:
        if isinstance(value, str):
            import json

            try:
                parsed = json.loads(value)
                return parsed if isinstance(parsed, dict) else {}
            except Exception:
                return {}
        if value is None:
            return {}
        return value

    @field_validator("value", "unit", "source_file", mode="before")
    @classmethod
    def validate_nullable_obs(cls, value: Any) -> Any:
        import math

        if value is None or (isinstance(value, float) and math.isnan(value)):
            return None
        return value

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
    nature: str
    nature_reviewed: bool = False
    alignment_override: str | None = None

    @field_validator("series_code", "unit", "description", mode="before")
    @classmethod
    def validate_nullable_meta(cls, value: Any) -> Any:
        import math

        if value is None or (isinstance(value, float) and math.isnan(value)):
            return None
        return value

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

    @field_validator("nature")
    @classmethod
    def validate_nature(cls, value: str) -> str:
        if value not in VALID_NATURES:
            raise ValueError(
                f"Unsupported series nature: {value!r}"
            )
        return value

    @field_validator("alignment_override")
    @classmethod
    def validate_alignment_override(
        cls,
        value: str | None,
    ) -> str | None:
        if (
            value is not None
            and value not in VALID_ALIGNMENT_OVERRIDES
        ):
            raise ValueError(
                f"Unsupported alignment_override: {value!r}"
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
