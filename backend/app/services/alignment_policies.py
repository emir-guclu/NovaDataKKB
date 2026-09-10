"""Nature-driven alignment policy resolution.

Alignment behaviour is derived from canonical financial semantics rather than
provider/source names or arbitrary series-code keyword heuristics.

Rules:
- stock -> last
- flow -> sum
- rate -> mean
- price -> mean
- optional alignment_override may explicitly override the default
- missing/unclassified nature fails loudly
"""

from __future__ import annotations

import pandas as pd

from app.services.align_service import AlignmentPolicy
from app.services.series_nature import alignment_method_for_nature


def _clean_optional_string(value):
    """Normalize pandas/None optional metadata values."""

    if value is None:
        return None

    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass

    value = str(value).strip()

    if not value:
        return None

    return value


def resolve_alignment_policy(
    series_id: str,
    source: str,
    freq: str,
    nature: str | None = None,
    alignment_override: str | None = None,
    accumulation: str = "none",
) -> AlignmentPolicy | None:
    """Resolve D/W alignment policy from canonical financial metadata.

    `source` remains in the public signature for compatibility and provenance,
    but is deliberately not used to infer aggregation behaviour.
    """

    del source

    if freq not in {"D", "W"}:
        return None

    clean_nature = _clean_optional_string(nature)
    clean_override = _clean_optional_string(
        alignment_override
    )

    if (
        clean_nature is None
        or clean_nature == "unclassified"
    ):
        raise ValueError(
            f"Series {series_id!r} has missing/unclassified "
            "financial nature; alignment is not allowed."
        )

    clean_accumulation = _clean_optional_string(accumulation) or "none"

    if clean_accumulation != "none":
        return AlignmentPolicy(method="last")

    method = alignment_method_for_nature(
        clean_nature,
        clean_override,
    )

    return AlignmentPolicy(method=method)


def build_alignment_policies(
    metadata_rows: pd.DataFrame,
) -> dict[str, AlignmentPolicy]:
    """Build a complete policy map for every D/W series."""

    required = {
        "series_id",
        "source",
        "freq",
        "nature",
    }

    missing = required - set(metadata_rows.columns)

    if missing:
        raise ValueError(
            "Alignment metadata is missing required columns: "
            + ", ".join(sorted(missing))
        )

    policies: dict[str, AlignmentPolicy] = {}

    for row in metadata_rows.to_dict("records"):
        freq = str(row["freq"])

        if freq not in {"D", "W"}:
            continue

        series_id = str(row["series_id"])

        policy = resolve_alignment_policy(
            series_id=series_id,
            source=str(row["source"]),
            freq=freq,
            nature=_clean_optional_string(
                row.get("nature")
            ),
            alignment_override=_clean_optional_string(
                row.get("alignment_override")
            ),
            accumulation=(
                _clean_optional_string(row.get("accumulation"))
                or "none"
            ),
        )

        if policy is None:
            raise ValueError(
                f"Could not resolve alignment policy "
                f"for series {series_id!r}"
            )

        policies[series_id] = policy

    return policies
