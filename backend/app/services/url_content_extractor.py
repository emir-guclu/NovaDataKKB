from __future__ import annotations

import base64
from dataclasses import dataclass, field
from io import BytesIO, StringIO
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import pandas as pd
import requests
from bs4 import BeautifulSoup

try:
    from pypdf import PdfReader
except ImportError:  # pragma: no cover - exercised when dependency is absent
    PdfReader = None

from backend.app.core.llm_provider import KloudeksProvider


MAX_BYTES = 15 * 1024 * 1024
TIMEOUT_SECONDS = 15
USER_AGENT = "NOVA-Analytics-Agent/1.0"


@dataclass
class ExtractedContent:
    content_type: str
    title: str | None
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)
    success: bool = True
    error: str | None = None


def extract_url_content(
    url: str,
    provider: KloudeksProvider | None = None,
) -> ExtractedContent:
    try:
        _validate_url(url)
        body, content_type, final_url = _download(url)
        kind = _detect_kind(final_url, content_type)

        if kind == "html":
            return _extract_html(body, content_type)
        if kind == "csv":
            return _extract_csv(body)
        if kind == "excel":
            return _extract_excel(body)
        if kind == "image":
            return _extract_image(body, provider)
        if kind == "pdf":
            return _extract_pdf(body)
        if kind == "text":
            return ExtractedContent(
                content_type="text",
                title=None,
                text=body.decode(_charset_from_content_type(content_type), errors="replace"),
                metadata={"source_content_type": content_type},
            )

        return ExtractedContent(
            content_type=kind,
            title=None,
            text="",
            success=False,
            error=f"Desteklenmeyen icerik tipi: {content_type}",
            metadata={"source_content_type": content_type},
        )
    except Exception as exc:
        return ExtractedContent(
            content_type="unknown",
            title=None,
            text="",
            success=False,
            error=str(exc),
        )


def _validate_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Yalnizca http ve https URL'leri desteklenir.")


def _download(url: str) -> tuple[bytes, str, str]:
    response = requests.get(
        url,
        headers={"User-Agent": USER_AGENT},
        stream=True,
        timeout=TIMEOUT_SECONDS,
    )
    response.raise_for_status()

    content_length = response.headers.get("Content-Length")
    if content_length and int(content_length) > MAX_BYTES:
        raise ValueError("Icerik 15 MB sinirini asiyor.")

    chunks: list[bytes] = []
    total = 0
    for chunk in response.iter_content(chunk_size=8192):
        if not chunk:
            continue
        total += len(chunk)
        if total > MAX_BYTES:
            raise ValueError("Icerik 15 MB sinirini asiyor.")
        chunks.append(chunk)

    return b"".join(chunks), response.headers.get("Content-Type", ""), response.url


def _detect_kind(url: str, content_type: str) -> str:
    lowered_type = content_type.split(";", 1)[0].strip().lower()
    suffix = Path(urlparse(url).path).suffix.lower()

    if lowered_type in {"text/html", "application/xhtml+xml"} or suffix in {".html", ".htm"}:
        return "html"
    if lowered_type in {"text/csv", "application/csv"} or suffix == ".csv":
        return "csv"
    if lowered_type in {
        "application/vnd.ms-excel",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    } or suffix in {".xls", ".xlsx"}:
        return "excel"
    if lowered_type.startswith("image/") or suffix in {".png", ".jpg", ".jpeg", ".webp"}:
        return "image"
    if lowered_type == "application/pdf" or suffix == ".pdf":
        return "pdf"
    if lowered_type.startswith("text/"):
        return "text"
    return lowered_type or "unknown"


def _charset_from_content_type(content_type: str) -> str:
    for part in content_type.split(";")[1:]:
        key, _, value = part.strip().partition("=")
        if key.lower() == "charset" and value:
            return value
    return "utf-8"


def _extract_html(body: bytes, content_type: str) -> ExtractedContent:
    html = body.decode(_charset_from_content_type(content_type), errors="replace")
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer"]):
        tag.decompose()

    title = soup.title.get_text(" ", strip=True) if soup.title else None
    lines = [line.strip() for line in soup.get_text("\n").splitlines()]
    text = "\n".join(line for line in lines if line)

    return ExtractedContent(
        content_type="html",
        title=title,
        text=text,
        metadata={"source_content_type": content_type},
    )


def _extract_csv(body: bytes) -> ExtractedContent:
    frame = pd.read_csv(BytesIO(body))
    return ExtractedContent(
        content_type="csv",
        title=None,
        text=_format_table_section(frame),
        metadata={"row_count": int(len(frame)), "columns": list(frame.columns)},
    )


def _extract_excel(body: bytes) -> ExtractedContent:
    workbook = pd.read_excel(BytesIO(body), sheet_name=None)
    sections: list[str] = []
    for sheet_name, frame in workbook.items():
        sections.append(f"Sheet: {sheet_name}\n{_format_table_section(frame)}")

    return ExtractedContent(
        content_type="excel",
        title=None,
        text="\n\n".join(sections),
        metadata={"sheets": list(workbook.keys())},
    )


def _extract_image(body: bytes, provider: KloudeksProvider | None) -> ExtractedContent:
    ocr_provider = provider or KloudeksProvider()
    image_base64 = base64.b64encode(body).decode("utf-8")
    text = ocr_provider.ocr(image_base64)
    return ExtractedContent(content_type="image", title=None, text=text)


def _extract_pdf(body: bytes) -> ExtractedContent:
    if PdfReader is None:
        return ExtractedContent(
            content_type="pdf",
            title=None,
            text="",
            success=False,
            error="PDF destegi icin pypdf paketi gereklidir.",
        )

    reader = PdfReader(BytesIO(body))
    page_texts = []
    for index, page in enumerate(reader.pages, start=1):
        page_texts.append(f"Page {index}\n{page.extract_text() or ''}".strip())

    return ExtractedContent(
        content_type="pdf",
        title=None,
        text="\n\n".join(page_texts),
        metadata={"page_count": len(reader.pages)},
    )


def _format_table_section(frame: pd.DataFrame) -> str:
    parts = [
        f"row_count: {len(frame)}",
        "columns: " + ", ".join(str(column) for column in frame.columns),
        _to_markdown(frame.head(15)),
    ]

    numeric_summary = frame.select_dtypes(include="number").agg(["min", "max", "mean"])
    if not numeric_summary.empty:
        parts.append("statistics:\n" + _to_markdown(numeric_summary.reset_index(names="metric")))

    return "\n\n".join(parts)


def _to_markdown(frame: pd.DataFrame) -> str:
    columns = [str(column) for column in frame.columns]
    rows = [[_format_cell(value) for value in row] for row in frame.itertuples(index=False, name=None)]

    output = StringIO()
    output.write("| " + " | ".join(columns) + " |\n")
    output.write("| " + " | ".join("---" for _ in columns) + " |\n")
    for row in rows:
        output.write("| " + " | ".join(row) + " |\n")
    return output.getvalue().rstrip()


def _format_cell(value: Any) -> str:
    if pd.isna(value):
        return ""
    return str(value)
