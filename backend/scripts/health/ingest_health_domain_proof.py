from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[3]

BRONZE = ROOT / "data" / "bronze" / "health" / "hospital_beds_total.csv"
SILVER_DIR = ROOT / "data" / "silver" / "health"
OBSERVATIONS = SILVER_DIR / "observations.parquet"
METADATA = SILVER_DIR / "series_metadata.parquet"

SERIES_ID = "HEALTH_MOH:hospital_beds_total"
SOURCE = "HEALTH_MOH"


def main() -> None:
    if not BRONZE.exists():
        raise FileNotFoundError(f"Bronze health file not found: {BRONZE}")

    raw = pd.read_csv(BRONZE)

    expected = {"year", "total_hospital_beds"}
    if set(raw.columns) != expected:
        raise ValueError(
            f"Unexpected Bronze columns: {list(raw.columns)}; expected {sorted(expected)}"
        )

    if raw["year"].duplicated().any():
        raise ValueError("Duplicate health years found.")

    raw = raw.sort_values("year").reset_index(drop=True)

    dates = pd.to_datetime(raw["year"].astype(str) + "-12-31").dt.date

    observations = pd.DataFrame(
        {
            "series_id": SERIES_ID,
            "source": SOURCE,
            "date": dates,
            "period_start": pd.to_datetime(
                raw["year"].astype(str) + "-01-01"
            ).dt.date,
            "period_end": dates,
            "value": raw["total_hospital_beds"].astype(float),
            "freq": "Y",
            "unit": "adet",
            "dims": [json.dumps({}, ensure_ascii=False)] * len(raw),
            "source_file": str(BRONZE.relative_to(ROOT)),
        }
    )

    metadata = pd.DataFrame(
        [
            {
                "series_id": SERIES_ID,
                "source": SOURCE,
                "series_code": "hospital_beds_total",
                "series_name": "Türkiye Toplam Hastane Yatağı Sayısı",
                "category": "Sağlık Altyapısı",
                "freq": "Y",
                "unit": "adet",
                "description": (
                    "Türkiye genelinde tüm sektörlerde toplam hastane yatağı sayısı. "
                    "Kaynak: T.C. Sağlık Bakanlığı Sağlık İstatistikleri Yıllığı 2024, "
                    "Şekil 7.2; Sağlık Hizmetleri Genel Müdürlüğü."
                ),
                "tags": [
                    "sağlık",
                    "hastane",
                    "yatak",
                    "sağlık altyapısı",
                    "Türkiye",
                ],
                "accumulation": "none",
                "is_cumulative": False,
                "nature": "stock",
                "nature_reviewed": True,
                "alignment_override": None,
            }
        ]
    )

    SILVER_DIR.mkdir(parents=True, exist_ok=True)
    observations.to_parquet(OBSERVATIONS, index=False)
    metadata.to_parquet(METADATA, index=False)

    print(f"Wrote {len(observations)} observations -> {OBSERVATIONS}")
    print(f"Wrote {len(metadata)} metadata row -> {METADATA}")


if __name__ == "__main__":
    main()
