from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, Iterable

import duckdb
import pandas as pd

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv(PROJECT_ROOT / ".env")

from backend.app.core.llm_provider import KloudeksProvider, LLMProvider

logger = logging.getLogger(__name__)

DEFAULT_SILVER_DB = PROJECT_ROOT / "data" / "silver" / "silver.duckdb"
DEFAULT_METADATA_RAW = PROJECT_ROOT / "data" / "bronze" / "evds" / "metadata_raw.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "gold" / "series_embeddings.parquet"


def _load_evds_metadata(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"EVDS metadata JSON object olmali: {path}")
    return {str(key): value for key, value in data.items() if isinstance(value, dict)}


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _normalise_tags(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    try:
        if pd.isna(value):
            return []
    except (TypeError, ValueError):
        pass
    if isinstance(value, Iterable) and not isinstance(value, (str, bytes, dict)):
        return [str(item) for item in value if str(item).strip()]
    return [part.strip() for part in str(value).split(",") if part.strip()]


def _summarise_dims(values: Any) -> str:
    if values is None:
        return "{}"

    seen: set[str] = set()
    parts: list[str] = []
    for raw in values:
        if raw is None:
            continue
        if isinstance(raw, dict):
            dims = raw
        else:
            try:
                dims = json.loads(str(raw))
            except json.JSONDecodeError:
                text = str(raw).strip()
                if text and text not in seen:
                    seen.add(text)
                    parts.append(text)
                continue
        if not isinstance(dims, dict) or not dims:
            continue
        for key, value in sorted(dims.items()):
            item = f"{key}={value}"
            if item not in seen:
                seen.add(item)
                parts.append(item)

    return "; ".join(parts) if parts else "{}"


def _semantic_text(row: dict[str, Any]) -> str:
    tags = ", ".join(_normalise_tags(row.get("tags")))
    return "\n".join(
        [
            f"Kaynak Kurum: {_clean_text(row.get('source'))} | Frekans: {_clean_text(row.get('freq'))} | Nitelik: {_clean_text(row.get('nature'))}",
            f"Seri Kodu: {_clean_text(row.get('series_code'))} | Seri ID: {_clean_text(row.get('series_id'))}",
            f"Seri Adi: {_clean_text(row.get('series_name'))} | Ingilizce Adi: {_clean_text(row.get('series_name_eng'))}",
            f"Kategori & Veri Grubu: {_clean_text(row.get('category'))} - {_clean_text(row.get('datagroup_name'))}",
            (
                f"Birim: {_clean_text(row.get('unit'))} | Gozlem Sayisi: {_clean_text(row.get('obs_count'))} | "
                f"Tarih Araligi: {_clean_text(row.get('start_date'))} - {_clean_text(row.get('end_date'))}"
            ),
            f"Boyut Kirilimlari: {_clean_text(row.get('dims_summary'))}",
            f"Aciklama / Metodoloji Notu: {_clean_text(row.get('description'))}",
            f"Etiketler: {tags}",
        ]
    )


def _fetch_catalog_rows(silver_db_path: Path, metadata_raw_path: Path) -> list[dict[str, Any]]:
    if not silver_db_path.exists():
        raise FileNotFoundError(f"Silver DuckDB bulunamadi: {silver_db_path}")

    evds_metadata = _load_evds_metadata(metadata_raw_path)
    con = duckdb.connect(str(silver_db_path), read_only=True)
    try:
        df = con.execute(
            """
            SELECT
                m.series_id,
                m.series_code,
                m.source,
                m.freq,
                m.nature,
                m.series_name,
                m.category,
                m.unit,
                m.description,
                m.tags,
                CAST(a.start_date AS VARCHAR) AS start_date,
                CAST(a.end_date AS VARCHAR) AS end_date,
                COALESCE(a.obs_count, 0) AS obs_count,
                a.dims_values
            FROM series_metadata AS m
            LEFT JOIN (
                SELECT
                    series_id,
                    MIN(date) AS start_date,
                    MAX(date) AS end_date,
                    COUNT(*) AS obs_count,
                    LIST(DISTINCT CAST(dims AS VARCHAR)) AS dims_values
                FROM observations
                GROUP BY series_id
            ) AS a USING (series_id)
            ORDER BY m.series_id
            """
        ).fetchdf()
    finally:
        con.close()

    records: list[dict[str, Any]] = []
    for raw in df.to_dict("records"):
        meta = evds_metadata.get(_clean_text(raw.get("series_code")), {})
        description = _clean_text(meta.get("NOTE")) or _clean_text(raw.get("description"))
        record = {
            "series_id": _clean_text(raw.get("series_id")),
            "series_code": _clean_text(raw.get("series_code")),
            "source": _clean_text(raw.get("source")),
            "freq": _clean_text(raw.get("freq")),
            "nature": _clean_text(raw.get("nature")),
            "series_name": _clean_text(raw.get("series_name")),
            "series_name_eng": _clean_text(meta.get("SERIE_NAME_ENG")),
            "category": _clean_text(raw.get("category")),
            "unit": _clean_text(raw.get("unit")),
            "start_date": _clean_text(raw.get("start_date")),
            "end_date": _clean_text(raw.get("end_date")),
            "obs_count": int(raw.get("obs_count") or 0),
            "dims_summary": _summarise_dims(raw.get("dims_values")),
            "description": description,
            "tags": _normalise_tags(raw.get("tags")),
            "datagroup_name": _clean_text(meta.get("DATAGROUP_NAME")),
        }
        record["semantic_text"] = _semantic_text(record)
        records.append(record)

    return records


def _embed_records(records: list[dict[str, Any]], provider: LLMProvider, batch_size: int) -> None:
    for start in range(0, len(records), batch_size):
        batch = records[start : start + batch_size]
        logger.info("Embedding catalog rows %s-%s/%s", start + 1, start + len(batch), len(records))
        texts = [record["semantic_text"] for record in batch]
        # Use batch API if available for massive speedup, otherwise fall back to iterative embed
        if hasattr(provider, "client") and hasattr(provider, "_with_rate_limit_retry"):
            try:
                response = provider._with_rate_limit_retry(
                    lambda: provider.client.embeddings.create(
                        model=getattr(provider, "EMBEDDING_MODEL", "Qwen/Qwen3-Embedding-8B"),
                        input=texts,
                        encoding_format="float",
                    )
                )
                for record, item in zip(batch, response.data):
                    record["embedding"] = item.embedding
                continue
            except Exception as err:
                logger.warning("Batch embedding failed (%s), falling back to iterative embed", err)

        for record in batch:
            record["embedding"] = provider.embed(record["semantic_text"])


def build_embedding_catalog(
    *,
    silver_db_path: str | Path = DEFAULT_SILVER_DB,
    metadata_raw_path: str | Path = DEFAULT_METADATA_RAW,
    output_path: str | Path = DEFAULT_OUTPUT,
    provider: LLMProvider | None = None,
    batch_size: int = 64,
) -> int:
    if batch_size < 1:
        raise ValueError("batch_size en az 1 olmali.")

    provider = provider or KloudeksProvider()
    records = _fetch_catalog_rows(Path(silver_db_path), Path(metadata_raw_path))
    _embed_records(records, provider, batch_size)

    output_columns = [
        "series_id",
        "series_code",
        "source",
        "freq",
        "nature",
        "series_name",
        "series_name_eng",
        "category",
        "unit",
        "start_date",
        "end_date",
        "obs_count",
        "dims_summary",
        "description",
        "tags",
        "embedding",
    ]
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(records)[output_columns].to_parquet(output, index=False)
    return len(records)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build semantic embeddings for the series catalog.")
    parser.add_argument("--silver-db", type=Path, default=DEFAULT_SILVER_DB)
    parser.add_argument("--metadata-raw", type=Path, default=DEFAULT_METADATA_RAW)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--batch-size", type=int, default=64)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    count = build_embedding_catalog(
        silver_db_path=args.silver_db,
        metadata_raw_path=args.metadata_raw,
        output_path=args.output,
        batch_size=args.batch_size,
    )
    logger.info("Wrote %s catalog embeddings to %s", count, args.output)


if __name__ == "__main__":
    main()
