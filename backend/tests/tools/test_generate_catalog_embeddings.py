from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pandas as pd

from backend.scripts import generate_catalog_embeddings

PROJECT_ROOT = Path(__file__).resolve().parents[3]
build_embedding_catalog = generate_catalog_embeddings.build_embedding_catalog


def test_generate_catalog_embeddings_defaults_point_to_project_data_paths():
    assert generate_catalog_embeddings.PROJECT_ROOT == PROJECT_ROOT
    assert generate_catalog_embeddings.DEFAULT_SILVER_DB == PROJECT_ROOT / "data" / "silver" / "silver.duckdb"
    assert generate_catalog_embeddings.DEFAULT_METADATA_RAW == PROJECT_ROOT / "data" / "bronze" / "evds" / "metadata_raw.json"
    assert generate_catalog_embeddings.DEFAULT_OUTPUT == PROJECT_ROOT / "data" / "gold" / "series_embeddings.parquet"


class FakeEmbeddingProvider:
    def __init__(self) -> None:
        self.texts: list[str] = []

    def embed(self, text: str) -> list[float]:
        self.texts.append(text)
        return [1.0, 0.0, 0.0]


def test_build_embedding_catalog_writes_rich_parquet(tmp_path):
    silver_db = tmp_path / "silver.duckdb"
    metadata_raw = tmp_path / "metadata_raw.json"
    output_path = tmp_path / "series_embeddings.parquet"

    con = duckdb.connect(str(silver_db))
    try:
        con.execute(
            """
            CREATE TABLE series_metadata (
                series_id VARCHAR,
                source VARCHAR,
                series_code VARCHAR,
                series_name VARCHAR,
                category VARCHAR,
                freq VARCHAR,
                unit VARCHAR,
                description VARCHAR,
                tags VARCHAR[],
                nature VARCHAR
            )
            """
        )
        con.execute(
            """
            INSERT INTO series_metadata VALUES (
                'EVDS:TP.FG.J0',
                'EVDS',
                'TP.FG.J0',
                'Tuketici Fiyat Endeksi',
                'fiyat_endeksleri',
                'M',
                'Endeks',
                'Yerel aciklama',
                ['tufe', 'enflasyon'],
                'flow'
            )
            """
        )
        con.execute(
            """
            CREATE TABLE observations (
                series_id VARCHAR,
                date DATE,
                dims JSON
            )
            """
        )
        con.execute(
            """
            INSERT INTO observations VALUES
                ('EVDS:TP.FG.J0', DATE '2026-01-31', '{"province":"Istanbul"}'),
                ('EVDS:TP.FG.J0', DATE '2026-02-28', '{"province":"Ankara"}')
            """
        )
    finally:
        con.close()

    metadata_raw.write_text(
        json.dumps(
            {
                "TP.FG.J0": {
                    "SERIE_NAME_ENG": "Consumer Price Index",
                    "DATAGROUP_NAME": "Prices",
                    "NOTE": "Official CPI methodology",
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    provider = FakeEmbeddingProvider()

    written = build_embedding_catalog(
        silver_db_path=silver_db,
        metadata_raw_path=metadata_raw,
        output_path=output_path,
        provider=provider,
        batch_size=1,
    )

    assert written == 1
    df = pd.read_parquet(output_path)
    row = df.iloc[0].to_dict()
    assert row["series_id"] == "EVDS:TP.FG.J0"
    assert row["series_name_eng"] == "Consumer Price Index"
    assert row["category"] == "fiyat_endeksleri"
    assert row["start_date"] == "2026-01-31"
    assert row["end_date"] == "2026-02-28"
    assert row["obs_count"] == 2
    assert "province=Ankara" in row["dims_summary"]
    assert list(row["embedding"]) == [1.0, 0.0, 0.0]
    assert "Official CPI methodology" in provider.texts[0]
    assert "Consumer Price Index" in provider.texts[0]
