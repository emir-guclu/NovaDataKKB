"""Build the cross-source canonical Silver DuckDB.

This script integrates source-specific EVDS and BDDK Silver artifacts
without modifying their original Parquet files.

Output:
    data/silver/silver.duckdb

Canonical tables:
    observations
    series_metadata
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]

SILVER_ROOT = ROOT / "data" / "silver"

EVDS_OBSERVATIONS = (
    SILVER_ROOT
    / "evds"
    / "observations.parquet"
)

EVDS_METADATA = (
    SILVER_ROOT
    / "evds"
    / "series_metadata.parquet"
)

BDDK_OBSERVATIONS = (
    SILVER_ROOT
    / "bddk"
    / "observations.parquet"
)

BDDK_METADATA = (
    SILVER_ROOT
    / "bddk"
    / "series_metadata.parquet"
)

OUTPUT_DB = (
    SILVER_ROOT
    / "silver.duckdb"
)


PROVINCE_CANONICAL = {
    "ADANA": ("Adana", "01"),
    "ADIYAMAN": ("Adıyaman", "02"),
    "AFYONKARAHİSAR": ("Afyonkarahisar", "03"),
    "AĞRI": ("Ağrı", "04"),
    "AMASYA": ("Amasya", "05"),
    "ANKARA": ("Ankara", "06"),
    "ANTALYA": ("Antalya", "07"),
    "ARTVİN": ("Artvin", "08"),
    "AYDIN": ("Aydın", "09"),
    "BALIKESİR": ("Balıkesir", "10"),
    "BİLECİK": ("Bilecik", "11"),
    "BİNGÖL": ("Bingöl", "12"),
    "BİTLİS": ("Bitlis", "13"),
    "BOLU": ("Bolu", "14"),
    "BURDUR": ("Burdur", "15"),
    "BURSA": ("Bursa", "16"),
    "ÇANAKKALE": ("Çanakkale", "17"),
    "ÇANKIRI": ("Çankırı", "18"),
    "ÇORUM": ("Çorum", "19"),
    "DENİZLİ": ("Denizli", "20"),
    "DİYARBAKIR": ("Diyarbakır", "21"),
    "EDİRNE": ("Edirne", "22"),
    "ELAZIĞ": ("Elazığ", "23"),
    "ERZİNCAN": ("Erzincan", "24"),
    "ERZURUM": ("Erzurum", "25"),
    "ESKİŞEHİR": ("Eskişehir", "26"),
    "GAZİANTEP": ("Gaziantep", "27"),
    "GİRESUN": ("Giresun", "28"),
    "GÜMÜŞHANE": ("Gümüşhane", "29"),
    "HAKKARİ": ("Hakkari", "30"),
    "HATAY": ("Hatay", "31"),
    "ISPARTA": ("Isparta", "32"),
    "MERSİN": ("Mersin", "33"),
    "İSTANBUL": ("İstanbul", "34"),
    "İZMİR": ("İzmir", "35"),
    "KARS": ("Kars", "36"),
    "KASTAMONU": ("Kastamonu", "37"),
    "KAYSERİ": ("Kayseri", "38"),
    "KIRKLARELİ": ("Kırklareli", "39"),
    "KIRŞEHİR": ("Kırşehir", "40"),
    "KOCAELİ": ("Kocaeli", "41"),
    "KONYA": ("Konya", "42"),
    "KÜTAHYA": ("Kütahya", "43"),
    "MALATYA": ("Malatya", "44"),
    "MANİSA": ("Manisa", "45"),
    "KAHRAMANMARAŞ": ("Kahramanmaraş", "46"),
    "MARDİN": ("Mardin", "47"),
    "MUĞLA": ("Muğla", "48"),
    "MUŞ": ("Muş", "49"),
    "NEVŞEHİR": ("Nevşehir", "50"),
    "NİĞDE": ("Niğde", "51"),
    "ORDU": ("Ordu", "52"),
    "RİZE": ("Rize", "53"),
    "SAKARYA": ("Sakarya", "54"),
    "SAMSUN": ("Samsun", "55"),
    "SİİRT": ("Siirt", "56"),
    "SİNOP": ("Sinop", "57"),
    "SİVAS": ("Sivas", "58"),
    "TEKİRDAĞ": ("Tekirdağ", "59"),
    "TOKAT": ("Tokat", "60"),
    "TRABZON": ("Trabzon", "61"),
    "TUNCELİ": ("Tunceli", "62"),
    "ŞANLIURFA": ("Şanlıurfa", "63"),
    "UŞAK": ("Uşak", "64"),
    "VAN": ("Van", "65"),
    "YOZGAT": ("Yozgat", "66"),
    "ZONGULDAK": ("Zonguldak", "67"),
    "AKSARAY": ("Aksaray", "68"),
    "BAYBURT": ("Bayburt", "69"),
    "KARAMAN": ("Karaman", "70"),
    "KIRIKKALE": ("Kırıkkale", "71"),
    "BATMAN": ("Batman", "72"),
    "ŞIRNAK": ("Şırnak", "73"),
    "BARTIN": ("Bartın", "74"),
    "ARDAHAN": ("Ardahan", "75"),
    "IĞDIR": ("Iğdır", "76"),
    "YALOVA": ("Yalova", "77"),
    "KARABÜK": ("Karabük", "78"),
    "KİLİS": ("Kilis", "79"),
    "OSMANİYE": ("Osmaniye", "80"),
    "DÜZCE": ("Düzce", "81"),
}


def _require(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(
            f"Required Silver artifact does not exist: {path}"
        )


def _normalize_province_name(raw: str) -> str:
    """Return canonical Turkish province name."""
    if raw == "YURT DIŞI":
        return "Yurt Dışı"

    if raw not in PROVINCE_CANONICAL:
        raise ValueError(
            f"Unknown FinTürk geography: {raw!r}"
        )

    return PROVINCE_CANONICAL[raw][0]


def normalize_dims(
    source: str,
    raw_dims: Any,
) -> str:
    """Normalize source-specific dimensions to canonical JSON keys."""
    if raw_dims is None or pd.isna(raw_dims):
        dims: dict[str, Any] = {}
    elif isinstance(raw_dims, dict):
        dims = dict(raw_dims)
    else:
        parsed = json.loads(str(raw_dims))

        if not isinstance(parsed, dict):
            raise ValueError(
                f"dims must decode to object, got {type(parsed).__name__}"
            )

        dims = parsed

    if source == "BDDK_FINTURK":
        canonical: dict[str, Any] = {}

        city = dims.get("sehir")

        if city:
            city_str = str(city).strip()

            canonical["province"] = (
                _normalize_province_name(
                    city_str
                )
            )

            if city_str == "YURT DIŞI":
                canonical["geo_level"] = "international"
            else:
                canonical["plate_code"] = (
                    PROVINCE_CANONICAL[city_str][1]
                )
                canonical["geo_level"] = "province"

        group = dims.get("grup")

        if group is not None:
            canonical["group"] = group

        # Preserve unexpected source dimensions without overriding
        # canonical keys.
        for key, value in dims.items():
            if key not in {"sehir", "grup"}:
                canonical.setdefault(
                    key,
                    value,
                )

        dims = canonical

    return json.dumps(
        dims,
        ensure_ascii=False,
        sort_keys=True,
    )


def _build_evds_observations() -> pd.DataFrame:
    obs = pd.read_parquet(
        EVDS_OBSERVATIONS
    )

    meta = pd.read_parquet(
        EVDS_METADATA
    )

    unit_map = (
        meta[
            [
                "series_id",
                "unit",
            ]
        ]
        .drop_duplicates("series_id")
    )

    obs = obs.merge(
        unit_map,
        on="series_id",
        how="left",
        validate="many_to_one",
    )

    # Canonical analytical date is always period_end.
    obs["date"] = pd.to_datetime(
        obs["period_end"]
    ).dt.date

    obs["period_start"] = pd.to_datetime(
        obs["period_start"]
    ).dt.date

    obs["period_end"] = pd.to_datetime(
        obs["period_end"]
    ).dt.date

    obs["source_file"] = None

    obs["dims"] = [
        normalize_dims(
            source,
            dims,
        )
        for source, dims in zip(
            obs["source"],
            obs["dims"],
        )
    ]

    return obs[
        [
            "series_id",
            "source",
            "date",
            "period_start",
            "period_end",
            "value",
            "freq",
            "unit",
            "dims",
            "source_file",
        ]
    ]


def _build_bddk_observations() -> pd.DataFrame:
    obs = pd.read_parquet(
        BDDK_OBSERVATIONS
    )

    obs["date"] = pd.to_datetime(
        obs["period_end"]
    ).dt.date

    obs["period_start"] = pd.to_datetime(
        obs["period_start"]
    ).dt.date

    obs["period_end"] = pd.to_datetime(
        obs["period_end"]
    ).dt.date

    obs["dims"] = [
        normalize_dims(
            source,
            dims,
        )
        for source, dims in zip(
            obs["source"],
            obs["dims"],
        )
    ]

    return obs[
        [
            "series_id",
            "source",
            "date",
            "period_start",
            "period_end",
            "value",
            "freq",
            "unit",
            "dims",
            "source_file",
        ]
    ]


def _build_evds_metadata() -> pd.DataFrame:
    meta = pd.read_parquet(
        EVDS_METADATA
    )

    result = pd.DataFrame(
        {
            "series_id": meta["series_id"],
            "source": meta["source"],
            "series_code": meta["series_code"],
            "series_name": meta["series_name"],
            "category": meta["category"],
            "freq": meta["freq"],
            "unit": meta["unit"],
            "description": meta["description"],
            "tags": meta["tags"],
            "accumulation": "none",
            "is_cumulative": False,
            "nature": meta["nature"],
            "nature_reviewed": meta["nature_reviewed"],
            "alignment_override": meta["alignment_override"],
        }
    )

    return result


def _bddk_category(
    series_id: str,
) -> str:
    parts = series_id.split(":")

    if len(parts) >= 3:
        return parts[1] if parts[1] != "t1" else "finturk"

    return "bddk"


def _bddk_series_code(
    series_id: str,
) -> str:
    return series_id.removeprefix(
        "BDDK_"
    )


def _bddk_series_name(
    series_id: str,
    description: str | None,
) -> str:
    if description:
        return str(description).split(
            " | ",
            1,
        )[0]

    return series_id


def _build_bddk_metadata() -> pd.DataFrame:
    meta = pd.read_parquet(
        BDDK_METADATA
    )

    result = pd.DataFrame(
        {
            "series_id": meta["series_id"],
            "source": meta["source"],
            "series_code": meta[
                "series_id"
            ].map(_bddk_series_code),
            "series_name": [
                _bddk_series_name(
                    series_id,
                    description,
                )
                for series_id, description in zip(
                    meta["series_id"],
                    meta["description"],
                )
            ],
            "category": meta[
                "series_id"
            ].map(_bddk_category),
            "freq": meta["freq"],
            "unit": meta["unit"],
            "description": meta["description"],
            "tags": [
                []
                for _ in range(len(meta))
            ],
            "accumulation": meta[
                "accumulation"
            ],
            "is_cumulative": meta[
                "is_cumulative"
            ],
            "nature": meta[
                "nature"
            ],
            "nature_reviewed": meta[
                "nature_reviewed"
            ],
            "alignment_override": meta[
                "alignment_override"
            ],
        }
    )

    return result


def main() -> None:
    for path in [
        EVDS_OBSERVATIONS,
        EVDS_METADATA,
        BDDK_OBSERVATIONS,
        BDDK_METADATA,
    ]:
        _require(path)

    print("Building canonical EVDS observations...")
    evds_obs = _build_evds_observations()

    print("Building canonical BDDK observations...")
    bddk_obs = _build_bddk_observations()

    observations = pd.concat(
        [
            evds_obs,
            bddk_obs,
        ],
        ignore_index=True,
    )

    print("Building canonical metadata...")
    metadata = pd.concat(
        [
            _build_evds_metadata(),
            _build_bddk_metadata(),
        ],
        ignore_index=True,
    )

    if observations.duplicated(
        [
            "series_id",
            "date",
            "dims",
        ]
    ).any():
        raise ValueError(
            "Canonical observations contain duplicate keys"
        )

    invalid_nature = metadata[
        metadata["nature"].isna()
        | (metadata["nature"] == "unclassified")
        | ~metadata["nature"].isin({"stock", "flow", "rate", "price"})
    ]

    if not invalid_nature.empty:
        sample = invalid_nature[["series_id", "nature"]].head(30)
        raise ValueError(
            "Canonical Silver build stopped because financial nature is missing/unclassified:\n"
            + sample.to_string(index=False)
        )

    if metadata["series_id"].duplicated().any():
        raise ValueError(
            "Canonical metadata contains duplicate series_id"
        )

    obs_ids = set(
        observations["series_id"]
    )

    meta_ids = set(
        metadata["series_id"]
    )

    if obs_ids != meta_ids:
        raise ValueError(
            "Observation and metadata series coverage mismatch: "
            f"missing_metadata={len(obs_ids - meta_ids)}, "
            f"orphan_metadata={len(meta_ids - obs_ids)}"
        )

    OUTPUT_DB.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    con = duckdb.connect(
        str(OUTPUT_DB)
    )

    try:
        con.register(
            "_canonical_observations",
            observations,
        )

        con.register(
            "_canonical_metadata",
            metadata,
        )

        con.execute(
            """
            CREATE OR REPLACE TABLE observations AS
            SELECT
                CAST(series_id AS VARCHAR) AS series_id,
                CAST(source AS VARCHAR) AS source,
                CAST(date AS DATE) AS date,
                CAST(period_start AS DATE) AS period_start,
                CAST(period_end AS DATE) AS period_end,
                CAST(value AS DOUBLE) AS value,
                CAST(freq AS VARCHAR) AS freq,
                CAST(unit AS VARCHAR) AS unit,
                CAST(dims AS JSON) AS dims,
                CAST(source_file AS VARCHAR) AS source_file
            FROM _canonical_observations
            """
        )

        con.execute(
            """
            CREATE OR REPLACE TABLE series_metadata AS
            SELECT
                CAST(series_id AS VARCHAR) AS series_id,
                CAST(source AS VARCHAR) AS source,
                CAST(series_code AS VARCHAR) AS series_code,
                CAST(series_name AS VARCHAR) AS series_name,
                CAST(category AS VARCHAR) AS category,
                CAST(freq AS VARCHAR) AS freq,
                CAST(unit AS VARCHAR) AS unit,
                CAST(description AS VARCHAR) AS description,
                tags,
                CAST(accumulation AS VARCHAR) AS accumulation,
                CAST(is_cumulative AS BOOLEAN) AS is_cumulative,
                CAST(nature AS VARCHAR) AS nature,
                CAST(nature_reviewed AS BOOLEAN) AS nature_reviewed,
                CAST(alignment_override AS VARCHAR) AS alignment_override
            FROM _canonical_metadata
            """
        )

        schema = con.execute(
            "DESCRIBE observations"
        ).fetchdf()

        stats = con.execute(
            """
            SELECT
                COUNT(*) AS rows,
                COUNT(DISTINCT series_id) AS series,
                COUNT(*) FILTER (
                    WHERE date <> period_end
                ) AS bad_dates,
                COUNT(*) FILTER (
                    WHERE dims IS NULL
                ) AS null_dims
            FROM observations
            """
        ).fetchdf()

        source_stats = con.execute(
            """
            SELECT
                source,
                freq,
                COUNT(*) AS rows,
                COUNT(DISTINCT series_id) AS series
            FROM observations
            GROUP BY source, freq
            ORDER BY source, freq
            """
        ).fetchdf()

        coverage = con.execute(
            """
            SELECT
                (
                    SELECT COUNT(*)
                    FROM (
                        SELECT DISTINCT series_id
                        FROM observations
                        EXCEPT
                        SELECT series_id
                        FROM series_metadata
                    )
                ) AS missing_metadata,
                (
                    SELECT COUNT(*)
                    FROM (
                        SELECT series_id
                        FROM series_metadata
                        EXCEPT
                        SELECT DISTINCT series_id
                        FROM observations
                    )
                ) AS orphan_metadata
            """
        ).fetchdf()

        finturk_sample = con.execute(
            """
            SELECT
                series_id,
                dims
            FROM observations
            WHERE source = 'BDDK_FINTURK'
            LIMIT 5
            """
        ).fetchdf()

        print()
        print("=" * 100)
        print("CANONICAL SILVER BUILD COMPLETE")
        print("=" * 100)

        print("\nSCHEMA:")
        print(
            schema.to_string(index=False)
        )

        print("\nSTATS:")
        print(
            stats.to_string(index=False)
        )

        print("\nBY SOURCE / FREQ:")
        print(
            source_stats.to_string(index=False)
        )

        print("\nCOVERAGE:")
        print(
            coverage.to_string(index=False)
        )

        print("\nFINTURK NORMALIZED DIMS SAMPLE:")
        print(
            finturk_sample.to_string(index=False)
        )

        print()
        print("DuckDB:", OUTPUT_DB)

    finally:
        con.close()


if __name__ == "__main__":
    main()
