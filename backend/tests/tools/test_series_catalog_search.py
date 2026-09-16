from __future__ import annotations

import math
from pathlib import Path

import duckdb

import pandas as pd
import pytest
from pydantic import ValidationError

from backend.app.agent.tool_registry import ToolRegistry, create_default_tool_registry
from backend.app.tools.series_catalog_search import SeriesCatalogSearchTool


class FakeEmbeddingProvider:
    def __init__(self, vectors: dict[str, list[float]]) -> None:
        self.vectors = vectors
        self.calls: list[str] = []

    def embed(self, text: str) -> list[float]:
        self.calls.append(text)
        return self.vectors[text]


def _write_embeddings(path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(path, index=False)


def test_series_catalog_search_ranks_matches_and_returns_rich_fields(tmp_path):
    embeddings_path = tmp_path / "series_embeddings.parquet"
    _write_embeddings(
        embeddings_path,
        [
            {
                "series_id": "BDDK_MONTHLY:tuketici_kredileri:tuketici_kredileri_tasit",
                "series_code": "tuketici_kredileri_tasit",
                "source": "BDDK_MONTHLY",
                "freq": "M",
                "nature": "stock",
                "series_name": "Tasit Kredileri",
                "series_name_eng": "",
                "category": "tuketici_kredileri",
                "unit": "Bin TL",
                "start_date": "2021-01-31",
                "end_date": "2026-07-31",
                "obs_count": 67,
                "dims_summary": "variable=Toplam",
                "description": "",
                "tags": ["tasit", "kredi"],
                "embedding": [1.0, 0.0, 0.0],
            },
            {
                "series_id": "EVDS:TP.FG.J0",
                "series_code": "TP.FG.J0",
                "source": "EVDS",
                "freq": "M",
                "nature": "flow",
                "series_name": "Tuketici Fiyat Endeksi",
                "series_name_eng": "Consumer Price Index",
                "category": "fiyat_endeksleri",
                "unit": "Endeks",
                "start_date": "2021-01-31",
                "end_date": "2026-07-31",
                "obs_count": 67,
                "dims_summary": "{}",
                "description": "Tufe",
                "tags": ["enflasyon"],
                "embedding": [0.5, 0.5, 0.0],
            },
        ],
    )
    provider = FakeEmbeddingProvider({"tasit kredisi hacmi": [0.9, 0.1, 0.0]})
    tool = SeriesCatalogSearchTool(provider=provider, embeddings_path=embeddings_path)

    result = tool.run(tool.Input(query="tasit kredisi hacmi", top_k=2, threshold=0.45))

    assert result.success is True
    assert result.found_in_lakehouse is True
    assert result.query == "tasit kredisi hacmi"
    assert len(result.matches) == 2
    assert result.matches[0].series_id == "BDDK_MONTHLY:tuketici_kredileri:tuketici_kredileri_tasit"
    assert result.matches[0].series_code == "tuketici_kredileri_tasit"
    assert result.matches[0].source == "BDDK_MONTHLY"
    assert result.matches[0].category == "tuketici_kredileri"
    assert result.matches[0].unit == "Bin TL"
    assert result.matches[0].freq == "M"
    assert result.matches[0].date_range == "2021-01-31 - 2026-07-31"
    assert result.matches[0].recommended_tool == "lakehouse_query"
    assert result.matches[0].similarity_score > result.matches[1].similarity_score
    assert math.isclose(result.best_match_score, result.matches[0].similarity_score)
    assert provider.calls == ["tasit kredisi hacmi"]


def test_series_catalog_search_below_threshold_suggests_external_evds(tmp_path):
    embeddings_path = tmp_path / "series_embeddings.parquet"
    _write_embeddings(
        embeddings_path,
        [
            {
                "series_id": "EVDS:TP.FG.J0",
                "series_code": "TP.FG.J0",
                "source": "EVDS",
                "freq": "M",
                "nature": "flow",
                "series_name": "Tuketici Fiyat Endeksi",
                "series_name_eng": "Consumer Price Index",
                "category": "fiyat_endeksleri",
                "unit": "Endeks",
                "start_date": "2021-01-31",
                "end_date": "2026-07-31",
                "obs_count": 67,
                "dims_summary": "{}",
                "description": "Tufe",
                "tags": ["enflasyon"],
                "embedding": [1.0, 0.0, 0.0],
            },
        ],
    )
    provider = FakeEmbeddingProvider({"platin londra metal borsasi": [0.0, 1.0, 0.0]})
    tool = SeriesCatalogSearchTool(provider=provider, embeddings_path=embeddings_path)

    result = tool.run(tool.Input(query="platin londra metal borsasi", threshold=0.45))

    assert result.success is True
    assert result.found_in_lakehouse is False
    assert result.best_match_score == 0.0
    assert result.matches == []
    assert "evds_data_service" in result.suggestion


def test_series_catalog_search_schema_and_registry_expose_tool():
    with pytest.raises(ValidationError):
        SeriesCatalogSearchTool.Input()

    registry = ToolRegistry()
    registry.register(SeriesCatalogSearchTool(provider=FakeEmbeddingProvider({})))

    schema = registry.to_openai_tools_format()[0]

    assert schema["function"]["name"] == "series_catalog_search"
    assert "query" in schema["function"]["parameters"]["properties"]
    assert "top_k" in schema["function"]["parameters"]["properties"]
    assert create_default_tool_registry().get("series_catalog_search") is not None


def _build_fallback_silver_db(path: Path) -> None:
    con = duckdb.connect(str(path))
    try:
        con.execute("CREATE TABLE series_metadata (series_id VARCHAR, source VARCHAR, series_code VARCHAR, series_name VARCHAR, category VARCHAR, freq VARCHAR, unit VARCHAR, description VARCHAR, tags VARCHAR[])")
        con.execute("CREATE TABLE observations (series_id VARCHAR, date DATE)")
        con.execute("INSERT INTO series_metadata VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", ["TEST:HOUSING", "TEST", "HOUSING", "Konut Kredisi Hacmi", "credit", "M", "milyon TL", "Konut kredisi toplam hacmi", ["konut", "kredi"]])
        con.execute("INSERT INTO series_metadata VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", ["TEST:GOLD", "TEST", "GOLD", "Altin Kapanis Fiyati", "commodity", "D", "USD/ons", "Altin piyasa fiyati", ["altin", "fiyat"]])
        con.execute("INSERT INTO observations VALUES (?, ?)", ["TEST:HOUSING", "2024-01-31"])
        con.execute("INSERT INTO observations VALUES (?, ?)", ["TEST:HOUSING", "2024-02-29"])
        con.execute("INSERT INTO observations VALUES (?, ?)", ["TEST:GOLD", "2024-01-02"])
    finally:
        con.close()


def test_series_catalog_search_falls_back_when_embeddings_missing(tmp_path: Path):
    silver_db = tmp_path / "silver.duckdb"
    _build_fallback_silver_db(silver_db)
    tool = SeriesCatalogSearchTool(embeddings_path=tmp_path / "missing.parquet", silver_db_path=silver_db)
    result = tool.run(tool.Input(query="konut kredisi", top_k=5))
    assert result.success is True
    assert result.found_in_lakehouse is True
    assert result.matches
    assert result.matches[0].series_id == "TEST:HOUSING"
    assert result.matches[0].unit == "milyon TL"
    assert result.matches[0].freq == "M"
    assert result.matches[0].date_range == "2024-01-31 - 2024-02-29"


def test_series_catalog_search_fallback_rejects_weak_unrelated_matches(tmp_path: Path):
    silver_db = tmp_path / "silver.duckdb"
    _build_fallback_silver_db(silver_db)
    tool = SeriesCatalogSearchTool(embeddings_path=tmp_path / "missing.parquet", silver_db_path=silver_db)
    result = tool.run(tool.Input(query="hasta sayisi", top_k=5))
    assert result.success is True
    assert result.found_in_lakehouse is False
    assert result.matches == []


def test_series_catalog_search_empty_query_without_catalog(tmp_path: Path):
    tool = SeriesCatalogSearchTool(embeddings_path=tmp_path / "missing.parquet", silver_db_path=tmp_path / "missing.duckdb")
    result = tool.run(tool.Input(query="   "))
    assert result.success is False
    assert result.error == "query bos olamaz."
