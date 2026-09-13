from __future__ import annotations

import base64
from dataclasses import dataclass, field
from io import BytesIO, StringIO
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

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
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)
REQUEST_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,application/pdf,*/*;q=0.8",
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
}
DOCUMENT_EXTENSIONS = {".pdf", ".xlsx", ".xls", ".csv", ".docx"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}


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
    render_js: bool = False,
) -> ExtractedContent:
    try:
        _validate_url(url)
        browser_warning = None
        if render_js:
            body, content_type, final_url, browser_warning = _fetch_with_browser(url)
            if body is None:
                raise ValueError(browser_warning or "Tarayici render islemi basarisiz oldu.")
            return _extract_html_v2(body, content_type, final_url, dynamic_warning=browser_warning)

        try:
            body, content_type, final_url = _download(url)
        except requests.HTTPError as exc:
            if getattr(exc.response, "status_code", None) != 403:
                raise
            body, content_type, final_url, browser_warning = _fetch_with_browser(url)
            if body is None:
                raise ValueError(browser_warning or "Statik istek 403 dondurdu ve browser fallback kullanilamadi.")

        kind = _detect_kind(final_url, content_type)

        if kind == "html":
            html_text = body.decode(_charset_from_content_type(content_type), errors="replace")
            if browser_warning is None and _looks_like_js_shell(html_text):
                browser_body, browser_type, browser_url, browser_error = _fetch_with_browser(final_url)
                if browser_body is not None:
                    body, content_type, final_url = browser_body, browser_type, browser_url
                    html_text = body.decode(_charset_from_content_type(content_type), errors="replace")
                else:
                    browser_warning = browser_error
            return _extract_html_v2(
                body,
                content_type,
                final_url,
                dynamic_warning=browser_warning,
            )
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
        headers=REQUEST_HEADERS,
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


def _fetch_with_browser(url: str) -> tuple[bytes | None, str, str, str | None]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None, "", url, "Playwright kurulu degil; dinamik sayfa statik HTML ile sinirli kaldi."

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(
                user_agent=USER_AGENT,
                extra_http_headers={
                    "Accept": REQUEST_HEADERS["Accept"],
                    "Accept-Language": REQUEST_HEADERS["Accept-Language"],
                },
            )
            response = page.goto(url, wait_until="domcontentloaded", timeout=TIMEOUT_SECONDS * 1000)
            page.wait_for_timeout(2500)
            html = page.content().encode("utf-8")
            final_url = page.url
            content_type = "text/html; charset=utf-8"
            if response is not None:
                header_value = response.headers.get("content-type")
                if header_value:
                    content_type = header_value
            browser.close()
            if len(html) > MAX_BYTES:
                return None, "", final_url, "Browser ile alinan icerik 15 MB sinirini asiyor."
            return html, content_type, final_url, None
    except Exception as exc:
        return None, "", url, f"Playwright fallback basarisiz oldu: {exc}"


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


def _looks_like_js_shell(html: str) -> bool:
    soup = BeautifulSoup(html, "html.parser")
    for container_id in ("root", "app"):
        container = soup.find(id=container_id)
        if container is not None and not container.get_text(" ", strip=True):
            return True

    visible_text = soup.get_text(" ", strip=True)
    has_script = soup.find("script") is not None
    has_static_content = soup.find(["h1", "h2", "h3", "p", "table", "a"]) is not None
    return has_script and not has_static_content and len(visible_text) < 300


def _extract_html_v2(
    body: bytes,
    content_type: str,
    base_url: str,
    *,
    dynamic_warning: str | None = None,
) -> ExtractedContent:
    html = body.decode(_charset_from_content_type(content_type), errors="replace")
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.get_text(" ", strip=True) if soup.title else None
    documents = _extract_document_links(soup, base_url)
    images = _extract_meaningful_images(soup, base_url)

    for tag in soup(["script", "style", "nav", "footer"]):
        tag.decompose()

    lines = [line.strip() for line in soup.get_text("\n").splitlines()]
    sections = ["\n".join(line for line in lines if line)]

    if documents:
        sections.append(
            "Bulunan Dosyalar\n"
            + "\n".join(f"- {document['label']}: {document['url']}" for document in documents)
        )

    if images:
        sections.append(
            "Sayfa Ici Gorseller / Semalar\n"
            + "\n".join(f"- {image['label']}: {image['url']}" for image in images)
        )

    if dynamic_warning:
        sections.append(f"Dinamik icerik uyarisi: {dynamic_warning}")

    return ExtractedContent(
        content_type="html",
        title=title,
        text="\n\n".join(section for section in sections if section),
        metadata={
            "source_content_type": content_type,
            "documents": documents,
            "images": images,
        },
    )


def _extract_html(body: bytes, content_type: str) -> ExtractedContent:
    return _extract_html_v2(body, content_type, "")


def _extract_document_links(soup: BeautifulSoup, base_url: str) -> list[dict[str, str]]:
    documents: list[dict[str, str]] = []
    seen: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        absolute_url = urljoin(base_url, anchor["href"])
        suffix = Path(urlparse(absolute_url).path).suffix.lower()
        if suffix not in DOCUMENT_EXTENSIONS or absolute_url in seen:
            continue
        label = anchor.get_text(" ", strip=True) or Path(urlparse(absolute_url).path).name
        documents.append({"label": label, "url": absolute_url})
        seen.add(absolute_url)
    return documents


def _extract_meaningful_images(soup: BeautifulSoup, base_url: str) -> list[dict[str, str]]:
    images: list[dict[str, str]] = []
    seen: set[str] = set()
    for image in soup.find_all("img", src=True):
        absolute_url = urljoin(base_url, image["src"])
        suffix = Path(urlparse(absolute_url).path).suffix.lower()
        label = (image.get("alt") or image.get("title") or "").strip()
        lowered = (label + " " + absolute_url).lower()
        if suffix not in IMAGE_EXTENSIONS or absolute_url in seen:
            continue
        if not label or "logo" in lowered or "icon" in lowered:
            continue
        images.append({"label": label, "url": absolute_url})
        seen.add(absolute_url)
    return images


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
