from __future__ import annotations

import logging
import re

import duckdb
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field

from dotenv import load_dotenv

from backend.app.core.llm_provider import KloudeksProvider, LLMProvider
from backend.app.tools.base import BaseTool

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(PROJECT_ROOT / ".env")
EMBEDDINGS_PARQUET = PROJECT_ROOT / "data" / "gold" / "series_embeddings.parquet"
SILVER_DB = PROJECT_ROOT / "data" / "silver" / "silver.duckdb"


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and np.isnan(value):
        return ""
    return str(value)


def _embedding_to_array(value: Any) -> np.ndarray:
    if isinstance(value, np.ndarray):
        return value.astype(np.float32)
    return np.asarray(list(value), dtype=np.float32)


class SeriesMatch(BaseModel):
    series_id: str
    series_code: str
    series_name: str
    source: str
    category: str
    unit: str
    freq: str
    date_range: str
    similarity_score: float
    recommended_tool: str


class SeriesCatalogSearchTool(BaseTool):
    name = "series_catalog_search"
    description = (
        "Lakehouse katalogundaki zaman serilerini ve gostergeleri dogal dil ile arar. "
        "Kullanici herhangi bir seri, gosterge, metrik, kategori veya veri kavrami sorup tam series_id "
        "bilinmediginde once bunu kullan. Ham veri getirmek icin KULLANMA; eslesen series_id ile "
        "lakehouse_query veya change_detection kullan."
    )

    class Input(BaseModel):
        query: str = Field(description="Dogal dille aranan seri, gosterge veya veri kavrami")
        top_k: int = Field(default=5, ge=1, le=5, description="Donulecek maksimum seri sayisi (en fazla 5)")
        threshold: float = Field(default=0.45, ge=-1.0, le=1.0, description="Minimum kosinus benzerlik esigi")

    class Output(BaseModel):
        success: bool
        error: str | None = None
        query: str
        found_in_lakehouse: bool = False
        best_match_score: float = 0.0
        matches: list[SeriesMatch] = Field(default_factory=list)
        suggestion: str = ""

    def __init__(
        self,
        *,
        provider: LLMProvider | None = None,
        embeddings_path: str | Path = EMBEDDINGS_PARQUET,
        silver_db_path: str | Path = SILVER_DB,
    ) -> None:
        self.provider = provider
        self.embeddings_path = Path(embeddings_path)
        self.silver_db_path = Path(silver_db_path)
        self._catalog: pd.DataFrame | None = None
        self._matrix: np.ndarray | None = None
        self._norms: np.ndarray | None = None

    def _get_provider(self) -> LLMProvider:
        if self.provider is None:
            self.provider = KloudeksProvider()
        return self.provider

    def _load_catalog(self) -> None:
        if self._catalog is not None and self._matrix is not None and self._norms is not None:
            return

        if not self.embeddings_path.exists():
            raise FileNotFoundError(f"Embedding parquet bulunamadi: {self.embeddings_path}")

        catalog = pd.read_parquet(self.embeddings_path)
        required_columns = {
            "series_id",
            "series_code",
            "source",
            "freq",
            "series_name",
            "category",
            "unit",
            "start_date",
            "end_date",
            "embedding",
        }
        missing = required_columns - set(catalog.columns)
        if missing:
            raise ValueError(f"Embedding katalog kolonlari eksik: {sorted(missing)}")
        if catalog.empty:
            raise ValueError("Embedding katalog bos.")

        vectors = [_embedding_to_array(value) for value in catalog["embedding"]]
        dimensions = {vector.shape[0] for vector in vectors}
        if len(dimensions) != 1:
            raise ValueError("Embedding vektor boyutlari tutarsiz.")

        matrix = np.vstack(vectors).astype(np.float32)
        norms = np.linalg.norm(matrix, axis=1)
        if np.any(norms == 0):
            raise ValueError("Embedding katalogunda sifir normlu vektor var.")

        self._catalog = catalog.reset_index(drop=True)
        self._matrix = matrix
        self._norms = norms

    @staticmethod
    def _normalise_tokens(text: str) -> list[str]:
        return [
            token
            for token in re.findall(r"\w+", text.casefold(), flags=re.UNICODE)
            if len(token) > 1
        ]

    def _fallback_metadata_search(self, params: Input) -> Output:
        if not self.silver_db_path.exists():
            return self.Output(
                success=False,
                error="Semantic embedding katalogu ve Silver metadata veritabani bulunamadi.",
                query=params.query,
                suggestion="Lakehouse veri katmanlarini olusturun veya katalogu yeniden uretin.",
            )

        tokens = self._normalise_tokens(params.query)
        if not tokens:
            return self.Output(
                success=False,
                error="query anlamli bir arama terimi icermiyor.",
                query=params.query,
            )

        con = duckdb.connect(str(self.silver_db_path), read_only=True)
        try:
            rows = con.execute(
                "SELECT "
                "m.series_id, "
                "COALESCE(m.series_code, '') AS series_code, "
                "COALESCE(m.series_name, '') AS series_name, "
                "COALESCE(m.source, '') AS source, "
                "COALESCE(m.category, '') AS category, "
                "COALESCE(m.unit, '') AS unit, "
                "COALESCE(m.freq, '') AS freq, "
                "COALESCE(m.description, '') AS description, "
                "COALESCE(CAST(m.tags AS VARCHAR), '') AS tags, "
                "CAST(MIN(o.date) AS VARCHAR) AS start_date, "
                "CAST(MAX(o.date) AS VARCHAR) AS end_date "
                "FROM series_metadata AS m "
                "LEFT JOIN observations AS o ON o.series_id = m.series_id "
                "GROUP BY m.series_id, m.series_code, m.series_name, m.source, "
                "m.category, m.unit, m.freq, m.description, m.tags"
            ).fetchdf()
        finally:
            con.close()

        query_cf = params.query.casefold().strip()
        ranked: list[tuple[float, Any]] = []
        for _, row in rows.iterrows():
            haystack = " ".join(
                _as_text(row.get(column))
                for column in [
                    "series_id", "series_code", "series_name", "source",
                    "category", "description", "tags",
                ]
            ).casefold()
            matched = sum(1 for token in tokens if token in haystack)
            if matched == 0:
                continue
            score = matched / len(tokens)
            if query_cf and query_cf in haystack:
                score = min(1.0, score + 0.15)

            # Lexical fallback is less expressive than semantic embeddings.
            # Require a stronger overlap to avoid false positives from generic
            # words such as "sayisi", "orani" or "degeri".
            effective_threshold = max(params.threshold, 0.60)
            if score < effective_threshold:
                continue

            ranked.append((score, row))

        ranked.sort(key=lambda item: item[0], reverse=True)
        matches: list[SeriesMatch] = []
        for score, row in ranked[: params.top_k]:
            matches.append(
                SeriesMatch(
                    series_id=_as_text(row.get("series_id")),
                    series_code=_as_text(row.get("series_code")),
                    series_name=_as_text(row.get("series_name")),
                    source=_as_text(row.get("source")),
                    category=_as_text(row.get("category")),
                    unit=_as_text(row.get("unit")),
                    freq=_as_text(row.get("freq")),
                    date_range=(
                        f"{_as_text(row.get('start_date'))} - "
                        f"{_as_text(row.get('end_date'))}"
                    ),
                    similarity_score=float(score),
                    recommended_tool="lakehouse_query",
                )
            )

        return self.Output(
            success=True,
            query=params.query,
            found_in_lakehouse=bool(matches),
            best_match_score=float(matches[0].similarity_score) if matches else 0.0,
            matches=matches,
            suggestion=(
                "Semantic embedding katalogu mevcut degildi; Silver metadata fallback aramasi kullanildi."
                if matches
                else "Silver metadata katalogunda eslesen seri bulunamadi."
            ),
        )

    def run(self, params: Input) -> Output:
        try:
            query = params.query.strip()
            if not query:
                return self.Output(
                    success=False,
                    error="query bos olamaz.",
                    query=params.query,
                    suggestion="Seri, gosterge veya veri kavramini dogal dille yazin.",
                )

            if not self.embeddings_path.exists():
                logger.warning(
                    "Embedding catalog missing at %s; using Silver metadata fallback search.",
                    self.embeddings_path,
                )
                return self._fallback_metadata_search(params)

            self._load_catalog()
            assert self._catalog is not None
            assert self._matrix is not None
            assert self._norms is not None

            query_vec = np.asarray(self._get_provider().embed(query), dtype=np.float32)
            if query_vec.shape[0] != self._matrix.shape[1]:
                return self.Output(
                    success=False,
                    error=(
                        "Sorgu embedding boyutu katalog ile uyumsuz: "
                        f"{query_vec.shape[0]} != {self._matrix.shape[1]}"
                    ),
                    query=params.query,
                )

            query_norm = float(np.linalg.norm(query_vec))
            if query_norm == 0.0:
                return self.Output(success=False, error="Sorgu embedding normu sifir.", query=params.query)

            scores = np.dot(self._matrix, query_vec) / (self._norms * query_norm)
            ranked_indices = np.argsort(scores)[::-1][: min(params.top_k, 5)]
            best_match_score = float(scores[ranked_indices[0]]) if len(ranked_indices) else 0.0

            matches: list[SeriesMatch] = []
            for idx in ranked_indices:
                score = float(scores[idx])
                if score < params.threshold:
                    continue
                row = self._catalog.iloc[int(idx)]
                matches.append(
                    SeriesMatch(
                        series_id=_as_text(row.get("series_id")),
                        series_code=_as_text(row.get("series_code")),
                        series_name=_as_text(row.get("series_name")),
                        source=_as_text(row.get("source")),
                        category=_as_text(row.get("category")),
                        unit=_as_text(row.get("unit")),
                        freq=_as_text(row.get("freq")),
                        date_range=f"{_as_text(row.get('start_date'))} - {_as_text(row.get('end_date'))}",
                        similarity_score=score,
                        recommended_tool="lakehouse_query",
                    )
                )

            found = bool(matches)
            suggestion = (
                "Eslesen series_id ile lakehouse_query veya degisim sorularinda change_detection kullanin."
                if found
                else (
                    "Bu veri yerel Lakehouse'da bulunamadi; harici veri cekmek icin "
                    "evds_data_service veya web_search aracini deneyin."
                )
            )

            return self.Output(
                success=True,
                query=params.query,
                found_in_lakehouse=found,
                best_match_score=best_match_score,
                matches=matches,
                suggestion=suggestion,
            )
        except Exception as exc:
            logger.exception("series_catalog_search failed")
            return self.Output(success=False, error=str(exc), query=params.query)
