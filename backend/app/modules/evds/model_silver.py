"""Canonical Silver Layer Data Models and PyArrow Schemas.

This module acts as the Single Source of Truth for all Silver-tier datasets:
- observations.parquet (Fact Table Schema)
- series_metadata.parquet (Dimension Table Schema)

Shared across EVDS, BDDK, and BIST modules to ensure cross-source schema uniformity.
"""

from datetime import date as dt_date
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field
import pyarrow as pa


# ==============================================================================
# 1. Pydantic Models (Validation, DTO & Agent Type Safety)
# ==============================================================================

class ObservationRecord(BaseModel):
    """Canonical Fact Table Model for Silver Observations."""
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    series_id: str = Field(
        ...,
        description="Universal canonical series identifier, e.g. 'EVDS:TP.KFE.TR10'",
        examples=["EVDS:TP.KFE.TR10", "EVDS:TP.KTF10"]
    )
    source: str = Field(
        default="EVDS",
        description="Data origin system (EVDS, BDDK, BIST)"
    )
    date: dt_date = Field(
        ...,
        description="Observation date"
    )
    period_start: dt_date = Field(
        ...,
        description="Standardized period start date (ISO Monday for weekly, 1st for monthly)"
    )
    period_end: dt_date = Field(
        ...,
        description="Standardized period end date (ISO Friday for weekly, last day for monthly)"
    )
    value: Optional[float] = Field(
        default=None,
        description="IEEE 754 float observation value (None for missing observations)"
    )
    freq: str = Field(
        ...,
        description="Canonical frequency code: D (Daily), W (Weekly), M (Monthly), Q (Quarterly), Y (Yearly)"
    )
    dims: str = Field(
        default="{}",
        description="JSON string containing structured dimensions (geo_level, region_code, province, currency, etc.)"
    )


class SeriesMetadataRecord(BaseModel):
    """Canonical Dimension Table Model for Silver Series Metadata."""
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    series_id: str = Field(
        ...,
        description="Universal canonical series identifier matching observations (JOIN key)"
    )
    series_code: str = Field(
        ...,
        description="Raw series code from data provider, e.g. 'TP.KFE.TR10'"
    )
    series_name: str = Field(
        ...,
        description="Official series title (double spaces stripped)"
    )
    category: str = Field(
        ...,
        description="Standardized ASCII slug derived from official datagroup name"
    )
    tcmb_category: Optional[str] = Field(
        default=None,
        description="Official high-level category name"
    )
    tcmb_datagroup: Optional[str] = Field(
        default=None,
        description="Official datagroup name"
    )
    freq: str = Field(
        ...,
        description="Canonical frequency code matching observations: D, W, M, Q, Y"
    )
    unit: Optional[str] = Field(
        default=None,
        description="Official unit of measurement"
    )
    description: Optional[str] = Field(
        default=None,
        description="Official methodology and definition note"
    )
    tags: List[str] = Field(
        default_factory=list,
        description="Search and classification tags"
    )
    source: str = Field(
        default="EVDS",
        description="Data origin system (EVDS, BDDK, BIST)"
    )

    nature: str = Field(
        ...,
        description=(
            "Financial nature: stock, flow, rate, price "
            "or unclassified"
        )
    )

    nature_reviewed: bool = Field(
        default=False,
        description="Whether financial nature has been explicitly reviewed"
    )

    alignment_override: Optional[str] = Field(
        default=None,
        description=(
            "Optional exceptional alignment method: "
            "last, sum or mean"
        )
    )


# ==============================================================================
# 2. PyArrow Table Schemas (Parquet Physical Storage Specification)
# ==============================================================================

OBSERVATIONS_SCHEMA = pa.schema([
    ("series_id", pa.string()),
    ("source", pa.string()),
    ("date", pa.date32()),
    ("period_start", pa.date32()),
    ("period_end", pa.date32()),
    ("value", pa.float64()),
    ("freq", pa.string()),
    ("dims", pa.string()),
])

SERIES_METADATA_SCHEMA = pa.schema([
    ("series_id", pa.string()),
    ("series_code", pa.string()),
    ("series_name", pa.string()),
    ("category", pa.string()),
    ("tcmb_category", pa.string()),
    ("tcmb_datagroup", pa.string()),
    ("freq", pa.string()),
    ("unit", pa.string()),
    ("description", pa.string()),
    ("tags", pa.list_(pa.string())),
    ("source", pa.string()),
    ("nature", pa.string()),
    ("nature_reviewed", pa.bool_()),
    ("alignment_override", pa.string()),
])
