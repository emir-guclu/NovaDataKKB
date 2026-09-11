"""Financial nature classification for canonical Silver series.

Nature describes the financial/economic behaviour of a series independently
from its provider.

Supported values:
- stock: balance, position, level, end-period quantity
- flow: amount generated/accumulated during a period
- rate: percentage/rate
- price: market price / exchange rate / unit price
- unclassified: intentionally unresolved; alignment must fail loudly

Unknown EVDS categories are deliberately left unclassified.
"""

from __future__ import annotations

from typing import Literal


Nature = Literal[
    "stock",
    "flow",
    "rate",
    "price",
    "unclassified",
]

AlignmentOverride = Literal[
    "last",
    "sum",
    "mean",
]


VALID_NATURES = {
    "stock",
    "flow",
    "rate",
    "price",
    "unclassified",
}

VALID_ALIGNMENT_OVERRIDES = {
    "last",
    "sum",
    "mean",
}


EVDS_PRICE_CATEGORIES = {
    "altin_fiyatlari_ankara_kuyumcular_ve_saatciler_odasi",
    "altin_piyasasi_bist",
    "doviz_kurlari",
    "gumus_piyasasi_bist",
    "degerlemesi_yapilan_konutlarin_birim_kiralari",
}

EVDS_RATE_CATEGORIES = {
    "imalat_sanayi_kapasite_kullanim_orani",
    "imalat_sanayi_kapasite_kullanim_orani_mevsimsellikten_arindirilmis",
    "kredi_faiz_oranlari_akim",
    "kredi_faiz_oranlari_stok",
    "mevduat_faiz_oranlari_akim",
    "temel_isgucu_gostergeleri_mevsimsellikten_arindirilmis",
}

EVDS_FLOW_CATEGORIES = {
    "altin_ithalati_bist",
    "altin_para_basimi_cumhuriyet_ve_resad_altini_gram_hmb_darphane",
    "konut_ve_is_yeri_satis_istatistikleri_ikinci_el_satislar",
    "konut_ve_is_yeri_satis_istatistikleri_ilk_el_satislar",
    "konut_ve_is_yeri_satis_istatistikleri_ipotekli_satislar",
    "konut_ve_is_yeri_satis_istatistikleri_toplam_satislar",
    "odemeler_dengesi_analitik_sunum",
}

EVDS_STOCK_CATEGORIES = {
    "krediler_bankacilik_sektoru",
    "krediler_katilim_bankalari",
    "krediler_mevduat_bankalari",
    "para_arzi_ve_karsilik_kalemleri",
    "toplam_uluslararasi_rezervler",
}

EVDS_INDEX_CATEGORIES = {
    "konut_fiyat_endeksi",
    "reel_efektif_doviz_kuru_tufe_bazli",
    "sanayi_uretim_endeksi_mevsim_ve_takvim_etkisinden_arindirilmis_tuik",
    "tuketici_fiyat_endeksi_genel_2003_100",
    "tuketici_guven_endeksi_ve_tuketici_egilim_endeksleri",
    "yeni_kiraci_kira_endeksi",
    "yurt_ici_uretici_fiyat_endeksi",
}


EVDS_SERIES_NATURE_OVERRIDES: dict[str, Nature] = {
    "EVDS:TP.APIFON1.IHA": "stock",
    "EVDS:TP.APIFON4": "rate",
}

EVDS_SERIES_ALIGNMENT_OVERRIDES: dict[str, AlignmentOverride] = {
    "EVDS:TP.APIFON1.IHA": "mean",
}


def alignment_method_for_nature(
    nature: str,
    alignment_override: str | None = None,
) -> AlignmentOverride:
    """Resolve aggregation method from financial semantics."""

    if alignment_override is not None:
        if alignment_override not in VALID_ALIGNMENT_OVERRIDES:
            raise ValueError(
                f"Invalid alignment_override: {alignment_override!r}"
            )
        return alignment_override  # type: ignore[return-value]

    if nature == "stock":
        return "last"

    if nature == "flow":
        return "sum"

    if nature in {"rate", "price"}:
        return "mean"

    raise ValueError(
        f"Nature {nature!r} is not classified. "
        "Series must be classified before alignment."
    )


def classify_evds_official_metadata_nature(
    *,
    unit: str | None,
    default_agg_method: str | None,
) -> tuple[Nature, AlignmentOverride | None]:
    """Conservatively classify unknown EVDS series from official metadata only.

    Series-name keyword matching is intentionally prohibited because names can
    contain conflicting financial concepts and create silent misclassification.
    Ambiguous metadata remains unclassified and must be reviewed explicitly.
    """
    unit_norm = str(unit or "").strip().upper()
    agg_norm = str(default_agg_method or "").strip().upper()

    signals: set[Nature] = set()

    if agg_norm == "KÜMÜLATİF":
        signals.add("flow")

    if unit_norm in {"%", "YÜZDE", "YUZDE", "ORAN", "PUAN"}:
        signals.add("rate")

    if len(signals) == 1:
        return next(iter(signals)), None

    return "unclassified", None


def classify_series_nature(
    *,
    series_id: str,
    source: str,
    category: str | None,
    accumulation: str = "none",
) -> tuple[Nature, AlignmentOverride | None]:
    """Return reviewed nature and optional alignment override."""

    category = str(category or "").strip()

    if source == "BDDK_MONTHLY":
        if accumulation != "none":
            return "stock", None

        if series_id.endswith("_periodic"):
            return "flow", None

        if category == "kar_zarar":
            return "flow", None

        if category in {
            "rasyolar",
            "yurt_disi_sube_rasyolari",
        }:
            return "rate", None

        return "stock", None

    if source == "BDDK_WEEKLY":
        return "stock", None

    if source == "BDDK_FINTURK":
        if category == "t5":
            return "rate", None
        return "stock", None

    if source == "EVDS":
        if series_id in EVDS_SERIES_NATURE_OVERRIDES:
            return (
                EVDS_SERIES_NATURE_OVERRIDES[series_id],
                EVDS_SERIES_ALIGNMENT_OVERRIDES.get(series_id),
            )

        if category in EVDS_PRICE_CATEGORIES:
            return "price", None

        if category in EVDS_RATE_CATEGORIES:
            return "rate", None

        if category in EVDS_FLOW_CATEGORIES:
            return "flow", None

        if category in EVDS_STOCK_CATEGORIES:
            return "stock", None

        if category in EVDS_INDEX_CATEGORIES:
            return "stock", "mean"

        return "unclassified", None

    return "unclassified", None
