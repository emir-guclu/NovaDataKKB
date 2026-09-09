"""Bronze EVDS Data Quality & Completeness Auditor.

Inspects all JSON series files in data/bronze/evds against series_manifest.yaml:
- Total records in Bronze
- Non-null values count & ratio (%)
- Missing/Null values count & ratio (%)
- First valid observation date & Last valid observation date
- Flags potential quality issues (late start, >20% missing, etc.)
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
import yaml

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("bronze_auditor")

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
BRONZE_DIR = BACKEND_DIR.parent / "data" / "bronze" / "evds"
MANIFEST_PATH = BACKEND_DIR / "app" / "modules" / "evds" / "series_manifest.yaml"


def extract_val_key(record: Dict[str, Any], series_code: str) -> Optional[str]:
    # Exact match first
    if series_code in record:
        return series_code
    # Sanitized match (EVDS replaces '.' with '_')
    clean_code = series_code.replace(".", "_")
    if clean_code in record:
        return clean_code
    # Fallback to any non-excluded key
    excluded = {"Tarih", "UNIXTIME", "YEARWEEK"}
    for k in record.keys():
        if k not in excluded:
            return k
    return None


def is_valid_value(val: Any) -> bool:
    if val is None:
        return False
    if isinstance(val, str):
        s = val.strip()
        if not s or s.lower() in ("null", "none", "nan", ""):
            return False
        try:
            float(s.replace(",", "."))
            return True
        except ValueError:
            return False
    if isinstance(val, (int, float)):
        import math
        return not math.isnan(val)
    return False


def main() -> None:
    if not MANIFEST_PATH.exists():
        logger.error(f"Manifest not found: {MANIFEST_PATH}")
        return

    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        manifest_data = yaml.safe_load(f)

    series_list = manifest_data.get("series", [])
    logger.info(f"\n{'='*110}")
    logger.info(f"BRONZE EVDS VERİ SAĞLIK VE DOLULUK DENETİMİ ({len(series_list)} Seri İnceleniyor)")
    logger.info(f"{'='*110}")
    logger.info(f"{'Seri Kodu':<26} | {'Frekans':<8} | {'Toplam':<6} | {'Dolu':<6} | {'Boş':<5} | {'Doluluk %':<9} | {'İlk Gözlem':<12} | {'Son Gözlem':<12} | {'Durum'}")
    logger.info(f"{'-'*110}")

    issues: List[Dict[str, Any]] = []
    success_count = 0

    for s in series_list:
        code = s["code"]
        freq = s.get("frequency", "-")
        json_path = BRONZE_DIR / f"{code}.json"

        if not json_path.exists():
            logger.warning(f"{code:<26} | {freq:<8} | {'YOK':<6} | {'-':<6} | {'-':<5} | {'0.0%':<9} | {'-':<12} | {'-':<12} | 🔴 DOSYA YOK!")
            issues.append({"code": code, "reason": "Dosya yok"})
            continue

        try:
            with open(json_path, "r", encoding="utf-8") as jf:
                records = json.load(jf)
        except Exception as e:
            logger.error(f"{code:<26} | {freq:<8} | ERROR: {e}")
            issues.append({"code": code, "reason": f"JSON parse hatası: {e}"})
            continue

        if not isinstance(records, list) or len(records) == 0:
            logger.warning(f"{code:<26} | {freq:<8} | {'0':<6} | {'0':<6} | {'0':<5} | {'0.0%':<9} | {'-':<12} | {'-':<12} | 🔴 BOŞ PAYLOAD")
            issues.append({"code": code, "reason": "Kayıt sayısı 0"})
            continue

        total = len(records)
        val_key = extract_val_key(records[0], code)

        valid_dates: List[str] = []
        valid_vals = 0

        for r in records:
            raw_v = r.get(val_key) if val_key else None
            tarih = r.get("Tarih")
            if is_valid_value(raw_v):
                valid_vals += 1
                if tarih:
                    valid_dates.append(str(tarih))

        null_count = total - valid_vals
        ratio = (valid_vals / total * 100) if total > 0 else 0.0
        first_dt = valid_dates[0] if valid_dates else "-"
        last_dt = valid_dates[-1] if valid_dates else "-"

        # Determine status
        status = "🟢 TAM DOLU"
        is_issue = False

        if ratio == 100.0:
            status = "🟢 %100 DOLU"
        elif ratio >= 90.0:
            status = f"🟡 %{ratio:.1f} DOLU (Normal tatil/haftasonu)"
        elif ratio >= 70.0:
            status = f"🟠 %{ratio:.1f} DOLU (Dikkat)"
            is_issue = True
        else:
            status = f"🔴 %{ratio:.1f} DOLU (Eksik Veri!)"
            is_issue = True

        # Check late start (e.g. starts after 2023)
        if first_dt != "-" and ("2024" in first_dt or "2025" in first_dt):
            status += " [GEÇ BAŞLANGIÇ!]"
            is_issue = True

        logger.info(f"{code:<26} | {freq:<8} | {total:<6} | {valid_vals:<6} | {null_count:<5} | {ratio:>7.1f}% | {first_dt:<12} | {last_dt:<12} | {status}")

        if is_issue:
            issues.append({"code": code, "name": s.get("name"), "ratio": ratio, "first": first_dt, "last": last_dt, "reason": status})
        else:
            success_count += 1

    logger.info(f"{'='*110}")
    logger.info(f"ÖZET RAPOR: {len(series_list)} seriden {success_count} tanesi KUSURSUZ/SAĞLIKLI.")
    if issues:
        logger.info(f"⚠️ İNCELENMESİ GEREKEN {len(issues)} SERİ BULUNDU:")
        for iss in issues:
            logger.info(f" - {iss['code']} ({iss.get('name', '')}): {iss['reason']} (İlk: {iss.get('first')}, Son: {iss.get('last')})")
    else:
        logger.info("🎉 HİÇBİR SERİDE SORUN BULUNAMADI! TÜM VERİLER HEDEF ARALIKTA EKSİKSİZ MEVCUT.")
    logger.info(f"{'='*110}\n")


if __name__ == "__main__":
    main()
