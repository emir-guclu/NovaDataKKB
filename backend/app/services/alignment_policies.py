"""Explicit alignment policies for real canonical Silver series.

No heuristic inference is performed here.

Rules:
- BDDK_WEEKLY observations are weekly stock/snapshot-style banking
  statistics, so monthly alignment uses the last observation in the month.
- EVDS rates, FX rates and daily TCMB funding indicators listed below are
  represented as monthly averages for Gold analytical features.
"""

from __future__ import annotations

from app.services.align_service import AlignmentPolicy


# All BDDK weekly tables currently represent reported balance / position
# snapshots rather than additive weekly flows.
BDDK_WEEKLY_POLICY = AlignmentPolicy(method="last")


EVDS_ALIGNMENT_POLICIES: dict[str, AlignmentPolicy] = {
    # Daily FX rates (buying and selling) -> monthly average rate.
    "EVDS:TP.DK.USD.A.YTL": AlignmentPolicy(method="mean"),
    "EVDS:TP.DK.USD.S.YTL": AlignmentPolicy(method="mean"),
    "EVDS:TP.DK.EUR.A.YTL": AlignmentPolicy(method="mean"),
    "EVDS:TP.DK.EUR.S.YTL": AlignmentPolicy(method="mean"),
    "EVDS:TP.DK.GBP.A.YTL": AlignmentPolicy(method="mean"),
    "EVDS:TP.DK.JPY.A.YTL": AlignmentPolicy(method="mean"),
    "EVDS:TP.DK.CHF.A.YTL": AlignmentPolicy(method="mean"),

    # Daily TCMB funding indicators -> monthly average level/cost.
    "EVDS:TP.APIFON1.IHA": AlignmentPolicy(method="mean"),
    "EVDS:TP.APIFON4": AlignmentPolicy(method="mean"),

    # Daily precious metals market prices -> monthly average.
    "EVDS:TP.ALTINPIYASA.KAP02": AlignmentPolicy(method="mean"),
    "EVDS:TP.ALTINPIYASA.KAP03": AlignmentPolicy(method="mean"),
    "EVDS:TP.GUMUSPIYASA.KAP03": AlignmentPolicy(method="mean"),

    # Weekly weighted-average credit interest rates -> monthly average.
    "EVDS:TP.KTF10": AlignmentPolicy(method="mean"),
    "EVDS:TP.KTF11": AlignmentPolicy(method="mean"),
    "EVDS:TP.KTF12": AlignmentPolicy(method="mean"),
    "EVDS:TP.KTF17": AlignmentPolicy(method="mean"),

    # Weekly weighted-average deposit interest rates (TRY & FX) -> monthly average.
    "EVDS:TP.TRY.MT01": AlignmentPolicy(method="mean"),
    "EVDS:TP.TRY.MT02": AlignmentPolicy(method="mean"),
    "EVDS:TP.TRY.MT03": AlignmentPolicy(method="mean"),
    "EVDS:TP.TRY.MT04": AlignmentPolicy(method="mean"),
    "EVDS:TP.TRY.MT05": AlignmentPolicy(method="mean"),
    "EVDS:TP.TRY.MT06": AlignmentPolicy(method="mean"),
    "EVDS:TP.USD.MT02": AlignmentPolicy(method="mean"),
    "EVDS:TP.EUR.MT02": AlignmentPolicy(method="mean"),
}


def resolve_alignment_policy(
    series_id: str,
    source: str,
    freq: str,
) -> AlignmentPolicy | None:
    """Return the explicit Gold alignment policy for a D/W series."""

    if freq not in {"D", "W"}:
        return None

    if source == "BDDK_WEEKLY":
        return BDDK_WEEKLY_POLICY

    return EVDS_ALIGNMENT_POLICIES.get(series_id)


def build_alignment_policies(
    metadata_rows,
) -> dict[str, AlignmentPolicy]:
    """Build a complete policy map from canonical metadata rows.

    Raises instead of silently guessing when a D/W series has no policy.
    """

    policies: dict[str, AlignmentPolicy] = {}
    missing: list[str] = []

    for row in metadata_rows.to_dict("records"):
        freq = str(row["freq"])

        if freq not in {"D", "W"}:
            continue

        series_id = str(row["series_id"])
        source = str(row["source"])

        policy = resolve_alignment_policy(
            series_id,
            source,
            freq,
        )

        if policy is None:
            missing.append(series_id)
        else:
            policies[series_id] = policy

    if missing:
        raise ValueError(
            "Missing explicit alignment policies for "
            f"{len(missing)} D/W series: "
            + ", ".join(sorted(missing))
        )

    return policies
