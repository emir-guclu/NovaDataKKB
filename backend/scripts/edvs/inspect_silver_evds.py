"""Inspect and summarize EVDS Silver Parquet datasets.

Reads data/silver/evds/observations.parquet and series_metadata.parquet,
printing a detailed overview and sample observations for every series.
"""

import sys
from pathlib import Path
import pandas as pd

# Set terminal display options
pd.set_option("display.max_columns", 10)
pd.set_option("display.width", 120)

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
SILVER_DIR = BACKEND_DIR.parent / "data" / "silver" / "evds"
OBS_PATH = SILVER_DIR / "observations.parquet"
META_PATH = SILVER_DIR / "series_metadata.parquet"


def inspect_silver() -> None:
    if not OBS_PATH.exists() or not META_PATH.exists():
        print(f"ERROR: Parquet files not found in {SILVER_DIR}")
        return

    obs = pd.read_parquet(OBS_PATH)
    meta = pd.read_parquet(META_PATH)

    print("=" * 90)
    print("           EVDS SILVER KATMANI GENEL VERİ VE ŞEMA ÖZETİ")
    print("=" * 90)
    print(f"Toplam Seri Sayısı        : {len(meta)}")
    print(f"Toplam Gözlem Sayısı      : {len(obs):,} satır")
    print(f"Frekans Dağılımı (Gözlem) : {obs['freq'].value_counts().to_dict()}")
    print(f"Frekans Dağılımı (Seri)   : {meta['freq'].value_counts().to_dict()}")
    print(f"Tarih Aralığı             : {obs['date'].min()} -> {obs['date'].max()}")
    print("=" * 90)

    # Join metadata with observations to show per-series summary
    for idx, (_, s) in enumerate(meta.iterrows(), 1):
        s_id = s["series_id"]
        s_obs = obs[obs["series_id"] == s_id].sort_values(by="date")

        valid_obs = s_obs[s_obs["value"].notna()]
        first_val = valid_obs.iloc[0] if not valid_obs.empty else None
        last_val = valid_obs.iloc[-1] if not valid_obs.empty else None

        desc_val = s["description"]
        desc = str(desc_val).strip() if pd.notna(desc_val) and str(desc_val).strip() else "Açıklama bulunamadı."
        desc_preview = (desc[:140] + "...") if len(desc) > 140 else desc

        tags_str = ", ".join(s["tags"][:5]) if s["tags"] is not None and len(s["tags"]) > 0 else "-"

        print(f"\n[{idx:02d}/22] {s_id} | {s['series_name']}")
        print("-" * 90)
        print(f"  * Kategori     : {s['category']} (TCMB Veri Grubu: {s['tcmb_datagroup']})")
        print(f"  * Frekans / Birim: {s['freq']} | {s['unit']}")
        print(f"  * Etiketler    : {tags_str}")
        print(f"  * Resmi Not    : {desc_preview}")
        print(f"  * Gözlem Sayısı: {len(s_obs)} satır (Dolu: {len(valid_obs)}, Boş: {len(s_obs) - len(valid_obs)})")

        if first_val is not None and last_val is not None:
            print(f"  * İlk Gözlem   : Tarih={first_val['date']} | Dönem=[{first_val['period_start']} -> {first_val['period_end']}] | Değer={first_val['value']}")
            print(f"  * Son Gözlem   : Tarih={last_val['date']} | Dönem=[{last_val['period_start']} -> {last_val['period_end']}] | Değer={last_val['value']}")
        else:
            print("  * Değer Durumu : Tüm gözlemler NaN")

    print("\n" + "=" * 90)
    print("                    İNCELEME BAŞARIYLA TAMAMLANDI")
    print("=" * 90)


if __name__ == "__main__":
    inspect_silver()
