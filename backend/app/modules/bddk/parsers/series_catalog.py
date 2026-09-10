"""Build deterministic BDDK Silver series catalog metadata."""

from __future__ import annotations

import re

import pandas as pd

from app.services.series_nature import classify_series_nature


VALID_ACCUMULATIONS = {
    "none",
    "ytd",
    "since_start",
}


# Explicitly reviewed cumulative series only.
#
# Do NOT populate this registry using monotonicity heuristics.
# A series is added only after manual semantic/data inspection.
ACCUMULATION_REGISTRY: dict[str, str] = {
    "BDDK_MONTHLY:kar_zarar:aktiflerimizin_satisindan_elde_edilen_gelirler": "ytd",
    "BDDK_MONTHLY:kar_zarar:alinan_kar_paylari": "ytd",
    "BDDK_MONTHLY:kar_zarar:amortisman_giderleri": "ytd",
    "BDDK_MONTHLY:kar_zarar:bankacilik_hizmetleri_gelirleri": "ytd",
    "BDDK_MONTHLY:kar_zarar:bankalara_verilen_faizler_giderler": "ytd",
    "BDDK_MONTHLY:kar_zarar:bankalardan_alinan_faizler_gelirler": "ytd",
    "BDDK_MONTHLY:kar_zarar:diger_faiz_disi_kar_payi_disindaki_gelirler": "ytd",
    "BDDK_MONTHLY:kar_zarar:diger_faiz_disi_kar_payi_disindaki_giderler": "ytd",
    "BDDK_MONTHLY:kar_zarar:diger_faiz_ve_faiz_benzeri_gelirler_diger_gelirler": "ytd",
    "BDDK_MONTHLY:kar_zarar:diger_faiz_ve_faiz_benzeri_giderler_diger_giderler": "ytd",
    "BDDK_MONTHLY:kar_zarar:diger_provizyonlar": "ytd",
    "BDDK_MONTHLY:kar_zarar:donem_net_kari_zarari_51_52": "ytd",
    "BDDK_MONTHLY:kar_zarar:finansal_kiralama_gelirleri": "ytd",
    "BDDK_MONTHLY:kar_zarar:finansal_kiralama_giderleri": "ytd",
    "BDDK_MONTHLY:kar_zarar:genel_karsilik_provizyonu": "ytd",
    "BDDK_MONTHLY:kar_zarar:gercege_uygun_deger_farki_k_z_yan_menk_deg_alinan_faizler": "ytd",
    "BDDK_MONTHLY:kar_zarar:gud_farki_diger_kapsamli_gelire_yansitilan_menkul_degerlerden_alinan_faizler": "ytd",
    "BDDK_MONTHLY:kar_zarar:ihrac_edilen_menkul_kiymetlere_verilen_faizler_odenen_kar_paylari": "ytd",
    "BDDK_MONTHLY:kar_zarar:itfa_edilmis_maliyeti_uzerinden_degerlenen_menkul_degerlerden_alinan_faizler": "ytd",
    "BDDK_MONTHLY:kar_zarar:kidem_tazminati_provizyonu": "ytd",
    "BDDK_MONTHLY:kar_zarar:kredilerden_alinan_faizler_kar_paylari": "ytd",
    "BDDK_MONTHLY:kar_zarar:kredilerden_alinan_faizler_kar_paylari:a_tuketici_kredilerinden_alinan_faizler_kar_paylari": "ytd",
    "BDDK_MONTHLY:kar_zarar:kredilerden_alinan_faizler_kar_paylari:b_kredi_kartlarindan_alinan_faizler_kar_paylari": "ytd",
    "BDDK_MONTHLY:kar_zarar:kredilerden_alinan_faizler_kar_paylari:c_taksitli_ticari_kredilerden_alinan_faizler_kar_paylari": "ytd",
    "BDDK_MONTHLY:kar_zarar:kredilerden_alinan_faizler_kar_paylari:d_diger_kredilerden_alinan_faizler_kar_paylari": "ytd",
    "BDDK_MONTHLY:kar_zarar:kredilerden_alinan_ucret_ve_komisyonlar": "ytd",
    "BDDK_MONTHLY:kar_zarar:kredilerden_alinan_ucret_ve_komisyonlar:a_nakdi_kredilerden_alinan_ucret_ve_komisyonlar": "ytd",
    "BDDK_MONTHLY:kar_zarar:kredilerden_alinan_ucret_ve_komisyonlar:b_gayrinakdi_kredilerden_alinan_ucret_ve_komisyonlar": "ytd",
    "BDDK_MONTHLY:kar_zarar:mevduata_verilen_faizler_katilim_fonlarina_odenen_kar_paylari": "ytd",
    "BDDK_MONTHLY:kar_zarar:net_faiz_kar_payi_geliri_gideri_15_23": "ytd",
    "BDDK_MONTHLY:kar_zarar:para_piy_isl_alinan_faizler": "ytd",
    "BDDK_MONTHLY:kar_zarar:para_piy_isl_verilen_faizler": "ytd",
    "BDDK_MONTHLY:kar_zarar:personel_giderleri": "ytd",
    "BDDK_MONTHLY:kar_zarar:prov_sonrasi_net_faiz_kar_payi_geliri_gideri_24_25": "ytd",
    "BDDK_MONTHLY:kar_zarar:repo_islemlerine_verilen_faizler": "ytd",
    "BDDK_MONTHLY:kar_zarar:takipteki_alacaklar_ozel_provizyonu": "ytd",
    "BDDK_MONTHLY:kar_zarar:takipteki_alacaklardan_alinan_faizler_kar_paylari": "ytd",
    "BDDK_MONTHLY:kar_zarar:ters_repo_islemlerinden_alinan_faizler": "ytd",
    "BDDK_MONTHLY:kar_zarar:toplam_faiz_disi_kar_payi_disindaki_gelirler_27_30_31_32_33": "ytd",
    "BDDK_MONTHLY:kar_zarar:toplam_faiz_disi_kar_payi_disindaki_giderler_35_44": "ytd",
    "BDDK_MONTHLY:kar_zarar:toplam_faiz_kar_payi_gelirleri_1_14_2_3_4_5": "ytd",
    "BDDK_MONTHLY:kar_zarar:toplam_faiz_kar_payi_giderleri_16_22": "ytd",
    "BDDK_MONTHLY:kar_zarar:vergi_oncesi_kar_zarar_26_34_50_45": "ytd",
    "BDDK_MONTHLY:kar_zarar:vergi_provizyonu": "ytd",
    "BDDK_MONTHLY:kar_zarar:vergi_resim_harc_ve_fonlar": "ytd",
    "BDDK_MONTHLY:kar_zarar:verilen_ucret_ve_komisyonlar": "ytd",
}

def get_accumulation(series_id: str) -> str:
    """Return reviewed accumulation classification for a series."""
    accumulation = ACCUMULATION_REGISTRY.get(
        series_id,
        "none",
    )

    if accumulation not in VALID_ACCUMULATIONS:
        raise ValueError(
            f"Invalid accumulation {accumulation!r} "
            f"for series {series_id}"
        )

    return accumulation


def _humanize_series_id(series_id: str) -> str:
    """
    Produce a deterministic fallback description.

    This is intentionally only a fallback. A richer description map can
    later replace it without changing series identity.
    """
    parts = series_id.split(":")

    meaningful = parts[1:] if len(parts) > 1 else parts

    text = " / ".join(
        part.replace("_", " ")
        for part in meaningful
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    ).strip()

    return text


def build_series_catalog(
    observations: pd.DataFrame,
) -> pd.DataFrame:
    """
    Build one catalog row per series_id.

    Required observation columns:
        series_id
        source
        freq
        unit

    Catalog columns:
        series_id
        source
        freq
        unit
        accumulation
        description
        is_cumulative
    """
    required = {
        "series_id",
        "source",
        "freq",
        "unit",
    }

    missing = required - set(observations.columns)

    if missing:
        raise ValueError(
            "Missing required observation columns for catalog: "
            f"{sorted(missing)}"
        )

    base = (
        observations[
            [
                "series_id",
                "source",
                "freq",
                "unit",
            ]
        ]
        .drop_duplicates()
        .reset_index(drop=True)
    )

    counts = (
        base.groupby(
            "series_id",
            dropna=False,
        )
        .size()
    )

    conflicting = counts[
        counts > 1
    ]

    if not conflicting.empty:
        bad_ids = conflicting.index.tolist()

        examples = (
            base[
                base["series_id"].isin(bad_ids)
            ]
            .sort_values("series_id")
            .head(30)
        )

        raise ValueError(
            "A series_id maps to multiple source/freq/unit "
            "combinations:\n"
            f"{examples.to_string(index=False)}"
        )

    if base["unit"].isna().any():
        raise ValueError(
            "Catalog cannot contain NULL units"
        )

    if (
        base["unit"]
        .astype(str)
        .str.strip()
        .eq("")
        .any()
    ):
        raise ValueError(
            "Catalog cannot contain blank units"
        )

    base["accumulation"] = (
        base["series_id"]
        .map(get_accumulation)
    )

    base["description"] = (
        base["series_id"]
        .map(_humanize_series_id)
    )

    finturk_mask = (
        base["source"] == "BDDK_FINTURK"
    )

    base.loc[
        finturk_mask,
        "description",
    ] = (
        base.loc[
            finturk_mask,
            "description",
        ]
        + " | dims.sehir = il/lokasyon bilgisi; "
        + "dims.grup = BDDK grup bilgisi"
    )

    base["is_cumulative"] = (
        base["accumulation"] != "none"
    )

    nature_results = []

    for row in base.itertuples(index=False):
        series_id = str(row.series_id)
        source = str(row.source)

        parts = series_id.split(":")
        category = parts[1] if len(parts) >= 2 else ""

        nature_results.append(
            classify_series_nature(
                series_id=series_id,
                source=source,
                category=category,
                accumulation=str(row.accumulation),
            )
        )

    base["nature"] = [
        result[0]
        for result in nature_results
    ]

    base["alignment_override"] = [
        result[1]
        for result in nature_results
    ]

    unclassified = base[
        base["nature"] == "unclassified"
    ]

    if not unclassified.empty:
        raise ValueError(
            "BDDK Silver build stopped because nature is "
            "unclassified for series: "
            + ", ".join(
                unclassified["series_id"]
                .astype(str)
                .head(30)
                .tolist()
            )
        )

    result = base[
        [
            "series_id",
            "source",
            "freq",
            "unit",
            "accumulation",
            "description",
            "is_cumulative",
            "nature",
            "alignment_override",
        ]
    ].sort_values(
        "series_id",
        kind="stable",
    ).reset_index(drop=True)

    if result["series_id"].duplicated().any():
        raise ValueError(
            "Series catalog contains duplicate series_id values"
        )

    return result
