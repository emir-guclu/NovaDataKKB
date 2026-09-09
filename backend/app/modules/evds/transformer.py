"""EVDS Silver Transformation Engine.

Transforms Bronze JSON series files and rich metadata into canonical Silver Parquet tables:
1. observations.parquet (Fact Table: series_id, source, date, period_start, period_end, value, freq, dims)
2. series_metadata.parquet (Dimension Table: series_id, series_code, series_name, category, tcmb_category,
                             tcmb_datagroup, freq, unit, description, tags, source)

Features:
- Zero-Manifest Dependency for values: all metadata is sourced from metadata_raw.json.
- Atomic parquet generation using temporary files and atomic rename.
- Incremental upsert and --full-refresh rebuild modes.
- Strict canonical schema adhering to section 5.4 specifications.
"""

import calendar
import json
import logging
import os
import re
import tempfile
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from app.modules.evds.metadata import load_manifest_series

logger = logging.getLogger(__name__)

DEFAULT_BRONZE_DIR = Path("data/bronze/evds")
DEFAULT_SILVER_DIR = Path("data/silver/evds")
DEFAULT_METADATA_JSON_PATH = Path("data/bronze/evds/metadata_raw.json")
from app.modules.evds.model_silver import OBSERVATIONS_SCHEMA, SERIES_METADATA_SCHEMA


FREQ_MAP = {
    "3 AYLIK": "Q",
    "ÇEYREKLİK": "Q",
    "CEYREKLIK": "Q",
    "HAFTALIK(CUMA)": "W",
    "HAFTALIK": "W",
    "GÜNLÜK": "D",
    "GUNLUK": "D",
    "AYLIK": "M",
    "YILLIK": "Y",
}


def slugify_turkish(text: Optional[str]) -> str:
    """Converts Turkish text into a standardized snake_case slug."""
    if not text:
        return "genel"
    t = text.strip()
    tr_map = str.maketrans({
        "ç": "c", "Ç": "c",
        "ğ": "g", "Ğ": "g",
        "ı": "i", "I": "i", "İ": "i",
        "ö": "o", "Ö": "o",
        "ş": "s", "Ş": "s",
        "ü": "u", "Ü": "u",
    })
    t = t.translate(tr_map).lower()
    t = re.sub(r"[^a-z0-9]+", "_", t)
    t = re.sub(r"_+", "_", t).strip("_")
    return t or "genel"


def resolve_canonical_freq(freq_str: Optional[str]) -> str:
    """Resolves canonical frequency code (D, W, M, Q, Y) from TCMB FREQUENCY_STR."""
    if not freq_str:
        return "D"
    normalized = freq_str.strip().upper()
    for key, code in FREQ_MAP.items():
        if key in normalized:
            return code
    return "D"


def parse_evds_date(tarih_str: str) -> Tuple[date, Optional[str]]:
    """Parses EVDS Tarih string into Python date object and detected format hints."""
    tarih_str = tarih_str.strip()
    # Case 1: DD-MM-YYYY (e.g. 04-01-2021)
    if re.match(r"^\d{2}-\d{2}-\d{4}$", tarih_str):
        return datetime.strptime(tarih_str, "%d-%m-%Y").date(), "daily"

    # Case 2: YYYY-M or YYYY-MM (e.g. 2021-1 or 2021-01)
    if re.match(r"^\d{4}-\d{1,2}$", tarih_str):
        parts = tarih_str.split("-")
        return date(int(parts[0]), int(parts[1]), 1), "monthly"

    # Case 3: YYYY-Q1..4 (e.g. 2021-Q1)
    if re.match(r"^\d{4}-Q[1-4]$", tarih_str, re.IGNORECASE):
        parts = tarih_str.split("-")
        year = int(parts[0])
        q_num = int(parts[1][1])
        month = (q_num - 1) * 3 + 1
        return date(year, month, 1), "quarterly"

    # Case 4: YYYY (e.g. 2021)
    if re.match(r"^\d{4}$", tarih_str):
        return date(int(tarih_str), 1, 1), "yearly"

    raise ValueError(f"Unrecognized EVDS Tarih format: '{tarih_str}'")


def compute_period_boundaries(dt: date, freq: str) -> Tuple[date, date]:
    """Computes standardized period_start and period_end for a given observation date and frequency.

    Rules (§3.1):
    - D (Daily): period_start = dt, period_end = dt
    - W (Weekly): period_start = Monday of the week, period_end = Friday (reported date)
    - M (Monthly): period_start = 1st day of month, period_end = last day of month
    - Q (Quarterly): period_start = 1st day of quarter, period_end = last day of quarter
    - Y (Yearly): period_start = Jan 1, period_end = Dec 31
    """
    if freq == "D":
        return dt, dt

    if freq == "W":
        # dt is reported Friday; period_start is Monday (dt - weekday days)
        monday = dt - timedelta(days=dt.weekday())
        return monday, dt

    if freq == "M":
        start = date(dt.year, dt.month, 1)
        _, last_day = calendar.monthrange(dt.year, dt.month)
        end = date(dt.year, dt.month, last_day)
        return start, end

    if freq == "Q":
        q = (dt.month - 1) // 3 + 1
        start_month = (q - 1) * 3 + 1
        end_month = q * 3
        start = date(dt.year, start_month, 1)
        _, last_day = calendar.monthrange(dt.year, end_month)
        end = date(dt.year, end_month, last_day)
        return start, end

    if freq == "Y":
        return date(dt.year, 1, 1), date(dt.year, 12, 31)

    return dt, dt


def clean_observation_value(raw_val: Any) -> Optional[float]:
    """Cleans raw string/numeric value into an IEEE 754 float or None for missing values."""
    if raw_val is None:
        return None
    if isinstance(raw_val, (int, float)):
        return float(raw_val) if not np.isnan(raw_val) else None

    val_str = str(raw_val).strip()
    if not val_str or val_str in ("-", "ND", "null", "None", "nan"):
        return None

    val_str = val_str.replace(",", ".")
    try:
        return float(val_str)
    except (ValueError, TypeError):
        return None


def extract_series_value_key(record: Dict[str, Any], series_code: str) -> Optional[str]:
    """Identifies the value key in a Bronze record dictionary."""
    expected_key = series_code.replace(".", "_")
    if expected_key in record:
        return expected_key

    # Fallback to key that is not Tarih, UNIXTIME, YEARWEEK
    excluded = {"Tarih", "UNIXTIME", "YEARWEEK"}
    for k in record.keys():
        if k not in excluded:
            return k
    return None


def extract_series_dims(series_code: str, meta_info: Dict[str, Any]) -> str:
    """Extracts semantic dimensions (geo, currency, loan/deposit type, commodity) into a JSON string."""
    dims: Dict[str, str] = {}

    # Regional Housing Price Index (KFE)
    kfe_regions = {
        "TR10": ("NUTS2", "İstanbul"),
        "TR51": ("NUTS2", "Ankara"),
        "TR31": ("NUTS2", "İzmir"),
        "TR41": ("NUTS2", "Bursa, Eskişehir, Bilecik"),
        "TR42": ("NUTS2", "Kocaeli, Sakarya, Düzce, Bolu, Yalova"),
        "TR61": ("NUTS2", "Antalya, Isparta, Burdur"),
        "TR62": ("NUTS2", "Adana, Mersin"),
        "TR21": ("NUTS2", "Edirne, Tekirdağ, Kırklareli"),
        "TR32": ("NUTS2", "Aydın, Denizli, Muğla"),
        "TR22": ("NUTS2", "Balıkesir, Çanakkale"),
        "TR33": ("NUTS2", "Manisa, Afyonkarahisar, Kütahya, Uşak"),
        "TR52": ("NUTS2", "Konya, Karaman"),
        "TR63": ("NUTS2", "Hatay, Kahramanmaraş, Osmaniye"),
        "TR7": ("NUTS1", "Orta Anadolu"),
        "TR8": ("NUTS1", "Batı Karadeniz"),
        "TR9": ("NUTS1", "Doğu Karadeniz"),
        "TRA": ("NUTS1", "Kuzeydoğu Anadolu"),
        "TRB": ("NUTS1", "Ortadoğu Anadolu"),
        "TRC": ("NUTS1", "Güneydoğu Anadolu"),
        "TR": ("NUTS0", "Türkiye Geneli"),
    }

    if series_code.startswith("TP.KFE."):
        reg_code = series_code.replace("TP.KFE.", "")
        if reg_code in kfe_regions:
            level, name = kfe_regions[reg_code]
            dims["geo_level"] = level
            dims["region_code"] = reg_code
            dims["region_name"] = name
            dims["market"] = "housing"
            dims["indicator"] = "price_index"

    # Housing Sales (Mortgaged, Total, First Hand, Second Hand)
    prov_map = {
        "100": ("İstanbul", "34"),
        "510": ("Ankara", "06"),
        "310": ("İzmir", "35"),
        "611": ("Antalya", "07"),
        "411": ("Bursa", "16"),
        "421": ("Kocaeli", "41"),
        "621": ("Adana", "01"),
        "TOPLAM": ("Türkiye", "TR"),
    }
    if "AKONUTSAT" in series_code:
        dims["market"] = "housing"
        dims["indicator"] = "sales_volume"
        if "AKONUTSAT1" in series_code:
            dims["sales_type"] = "total"
        elif "AKONUTSAT2" in series_code:
            dims["sales_type"] = "mortgaged"
        elif "AKONUTSAT3" in series_code:
            dims["sales_type"] = "first_hand"
        elif "AKONUTSAT4" in series_code:
            dims["sales_type"] = "second_hand"

        for suffix, (pname, pcode) in prov_map.items():
            if series_code.endswith(suffix):
                dims["province"] = pname
                dims["plate_code"] = pcode
                break

    # Rents
    if series_code.startswith("TP.BK.") or series_code == "TP.YKKE.TR":
        dims["market"] = "housing"
        dims["indicator"] = "rent"
        if "ISTANBUL" in series_code:
            dims["province"] = "İstanbul"
            dims["plate_code"] = "34"
        elif "ANKARA" in series_code:
            dims["province"] = "Ankara"
            dims["plate_code"] = "06"
        elif "IZMIR" in series_code:
            dims["province"] = "İzmir"
            dims["plate_code"] = "35"
        elif "TR" in series_code:
            dims["province"] = "Türkiye"

    # Currency
    if "USD" in series_code:
        dims["currency"] = "USD"
    elif "EUR" in series_code:
        dims["currency"] = "EUR"
    elif "TRY" in series_code or "YTL" in series_code:
        dims["currency"] = "TRY"
    elif "GBP" in series_code:
        dims["currency"] = "GBP"
    elif "CHF" in series_code:
        dims["currency"] = "CHF"
    elif "JPY" in series_code:
        dims["currency"] = "JPY"

    # Precious Metals
    if "ALTIN" in series_code or "GUMUS" in series_code or "GOLD" in series_code or series_code.startswith("TP.MK."):
        dims["commodity_group"] = "precious_metals"
        if "GUMUS" in series_code:
            dims["commodity"] = "silver"
        else:
            dims["commodity"] = "gold"

    return json.dumps(dims, ensure_ascii=False) if dims else "{}"


def transform_single_series(
    series_code: str,
    bronze_records: List[Dict[str, Any]],
    meta_info: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Transforms raw bronze JSON records for a single series into canonical observation rows."""
    freq_str = meta_info.get("FREQUENCY_STR")
    freq = resolve_canonical_freq(freq_str)
    series_id = f"EVDS:{series_code}"
    dims_str = extract_series_dims(series_code, meta_info)

    rows: List[Dict[str, Any]] = []

    for rec in bronze_records:
        if not isinstance(rec, dict) or "Tarih" not in rec:
            continue

        tarih_raw = rec["Tarih"]
        if not tarih_raw:
            continue

        try:
            obs_date, _ = parse_evds_date(tarih_raw)
        except Exception as exc:
            logger.debug(f"Skipping malformed date '{tarih_raw}' for {series_code}: {exc}")
            continue

        p_start, p_end = compute_period_boundaries(obs_date, freq)
        val_key = extract_series_value_key(rec, series_code)
        val = clean_observation_value(rec.get(val_key)) if val_key else None
        if val is None:
            continue

        rows.append({
            "series_id": series_id,
            "source": "EVDS",
            "date": obs_date,
            "period_start": p_start,
            "period_end": p_end,
            "value": val,
            "freq": freq,
            "dims": dims_str,
        })

    return rows


def build_series_dimension_row(series_code: str, meta: Dict[str, Any]) -> Dict[str, Any]:
    """Builds a single row for the silver_evds_series dimension table."""
    series_id = f"EVDS:{series_code}"
    freq_str = meta.get("FREQUENCY_STR")
    freq = resolve_canonical_freq(freq_str)
    dg_name = meta.get("DATAGROUP_NAME") or "Genel"
    cat_slug = slugify_turkish(dg_name)

    tag_val = meta.get("TAG")
    if isinstance(tag_val, list):
        tags = [str(t).strip() for t in tag_val if str(t).strip()]
    elif isinstance(tag_val, str) and tag_val:
        tags = [t.strip() for t in tag_val.split(",") if t.strip()]
    else:
        tags = []

    return {
        "series_id": series_id,
        "series_code": series_code,
        "series_name": meta.get("SERIE_NAME") or series_code,
        "category": cat_slug,
        "tcmb_category": meta.get("CATEGORY_NAME"),
        "tcmb_datagroup": dg_name,
        "freq": freq,
        "unit": meta.get("BIRIMI"),
        "description": meta.get("NOTE"),
        "tags": tags,
        "source": "EVDS",
    }


def write_parquet_atomic(table: pa.Table, target_path: Union[str, Path]) -> Path:
    """Atomically writes PyArrow Table to a Parquet file via temporary file and replace."""
    path = Path(target_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    temp_path = path.parent / f".tmp_{os.getpid()}_{uuid.uuid4().hex}.parquet"
    try:
        pq.write_table(table, temp_path, compression="snappy")
        os.replace(temp_path, path)
        logger.info(f"Atomically written {table.num_rows} rows to {path}")
        return path
    finally:
        if temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass


def transform_silver_evds(
    bronze_dir: Union[str, Path] = DEFAULT_BRONZE_DIR,
    metadata_json_path: Union[str, Path] = DEFAULT_METADATA_JSON_PATH,
    silver_dir: Union[str, Path] = DEFAULT_SILVER_DIR,
    manifest_path: Optional[Union[str, Path]] = None,
    full_refresh: bool = False,
) -> Tuple[Path, Path]:
    """Runs the complete Silver transformation pipeline.

    Args:
        bronze_dir: Directory containing raw bronze JSON files.
        metadata_json_path: Path to metadata_raw.json.
        silver_dir: Destination directory for observations.parquet and series_metadata.parquet.
        manifest_path: Optional path to series_manifest.yaml to filter specific series.
        full_refresh: If True, rebuilds the parquet tables completely from scratch.

    Returns:
        Tuple of (observations_parquet_path, series_metadata_parquet_path).
    """
    bronze_p = Path(bronze_dir)
    meta_p = Path(metadata_json_path)
    silver_p = Path(silver_dir)
    silver_p.mkdir(parents=True, exist_ok=True)

    obs_target = silver_p / "observations.parquet"
    meta_target = silver_p / "series_metadata.parquet"

    if not meta_p.exists():
        raise FileNotFoundError(
            f"Metadata file {meta_p} not found! Run app.modules.evds.metadata.sync_metadata() first."
        )

    with open(meta_p, "r", encoding="utf-8") as f:
        metadata_dict: Dict[str, Any] = json.load(f)

    # Determine target series codes
    if manifest_path:
        manifest_items = load_manifest_series(manifest_path)
        series_codes = [s["code"] for s in manifest_items if "code" in s]
    else:
        series_codes = list(metadata_dict.keys())

    logger.info(f"Starting Silver transform for {len(series_codes)} series (full_refresh={full_refresh})...")

    new_obs_records: List[Dict[str, Any]] = []
    new_dim_records: List[Dict[str, Any]] = []

    for code in series_codes:
        json_file = bronze_p / f"{code}.json"
        if not json_file.exists():
            logger.warning(f"Bronze JSON file for series {code} not found at {json_file}. Skipping.")
            continue

        try:
            with open(json_file, "r", encoding="utf-8") as f:
                records = json.load(f)
        except Exception as exc:
            logger.error(f"Failed to read bronze JSON for {code}: {exc}")
            continue

        meta_info = metadata_dict.get(code, {})
        obs_rows = transform_single_series(code, records, meta_info)
        new_obs_records.extend(obs_rows)

        dim_row = build_series_dimension_row(code, meta_info)
        new_dim_records.append(dim_row)

    if not new_obs_records:
        raise ValueError("No observation rows were produced! Check bronze files and metadata.")

    # Convert new observations to DataFrame
    new_obs_df = pd.DataFrame(new_obs_records)
    new_dim_df = pd.DataFrame(new_dim_records)

    # Merge or full refresh for observations
    if not full_refresh and obs_target.exists():
        logger.info(f"Existing {obs_target} found. Performing incremental upsert...")
        existing_obs_df = pd.read_parquet(obs_target)
        combined_obs_df = pd.concat([existing_obs_df, new_obs_df], ignore_index=True)
        # Drop duplicates on (series_id, date) keeping latest
        combined_obs_df = combined_obs_df.drop_duplicates(subset=["series_id", "date"], keep="last")
    else:
        combined_obs_df = new_obs_df

    # Deterministic sorting (series_id ASC, date ASC)
    combined_obs_df = combined_obs_df.sort_values(by=["series_id", "date"]).reset_index(drop=True)

    # Merge or full refresh for series metadata dimension
    if not full_refresh and meta_target.exists():
        existing_dim_df = pd.read_parquet(meta_target)
        combined_dim_df = pd.concat([existing_dim_df, new_dim_df], ignore_index=True)
        combined_dim_df = combined_dim_df.drop_duplicates(subset=["series_id"], keep="last")
    else:
        combined_dim_df = new_dim_df

    combined_dim_df = combined_dim_df.sort_values(by=["series_id"]).reset_index(drop=True)

    # Convert to PyArrow Tables with strict schemas
    obs_table = pa.Table.from_pandas(combined_obs_df, schema=OBSERVATIONS_SCHEMA, preserve_index=False)
    dim_table = pa.Table.from_pandas(combined_dim_df, schema=SERIES_METADATA_SCHEMA, preserve_index=False)

    # Atomic writes
    write_parquet_atomic(obs_table, obs_target)
    write_parquet_atomic(dim_table, meta_target)

    logger.info(
        f"Silver transformation complete! "
        f"Observations: {obs_table.num_rows} rows, Series Metadata: {dim_table.num_rows} series."
    )
    return obs_target, meta_target


if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    parser = argparse.ArgumentParser(description="Transform EVDS Bronze JSON to Silver Parquet.")
    parser.add_argument("--full-refresh", action="store_true", help="Rebuild silver parquets from scratch")
    args = parser.parse_args()
    transform_silver_evds(full_refresh=args.full_refresh)
