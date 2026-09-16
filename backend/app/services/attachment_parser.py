from __future__ import annotations

import base64
from io import StringIO
import logging
import os
from pathlib import Path
from typing import Any
import pandas as pd

try:
    from pypdf import PdfReader
except ImportError:  # pragma: no cover
    PdfReader = None

from backend.app.core.llm_provider import KloudeksProvider, NvidiaProvider, LLMProvider

logger = logging.getLogger(__name__)


def _format_cell(value: Any) -> str:
    if pd.isna(value):
        return ""
    return str(value)


def _to_markdown(frame: pd.DataFrame) -> str:
    columns = [str(column) for column in frame.columns]
    rows = [[_format_cell(value) for value in row] for row in frame.itertuples(index=False, name=None)]

    output = StringIO()
    output.write("| " + " | ".join(columns) + " |\n")
    output.write("| " + " | ".join("---" for _ in columns) + " |\n")
    for row in rows:
        output.write("| " + " | ".join(row) + " |\n")
    return output.getvalue().rstrip()


def _format_table_section(frame: pd.DataFrame) -> str:
    parts = [
        f"row_count: {len(frame)}",
        "columns: " + ", ".join(str(column) for column in frame.columns),
        _to_markdown(frame.head(25)),
    ]

    numeric_summary = frame.select_dtypes(include="number").agg(["min", "max", "mean"])
    if not numeric_summary.empty:
        parts.append("statistics:\n" + _to_markdown(numeric_summary.reset_index(names="metric")))

    return "\n\n".join(parts)


def parse_csv(file_path: Path) -> str:
    """CSV dosyasını dinamik ve hızlı ayraç tespiti ile okur ve Markdown formatına dönüştürür."""
    try:
        sample = file_path.read_text(encoding="utf-8", errors="ignore")[:4096]
        if sample.count(";") > sample.count(","):
            frame = pd.read_csv(file_path, sep=";")
        elif sample.count("\t") > sample.count(","):
            frame = pd.read_csv(file_path, sep="\t")
        else:
            frame = pd.read_csv(file_path, sep=",")
    except Exception:
        try:
            frame = pd.read_csv(file_path, sep=None, engine="python")
        except Exception:
            frame = pd.read_csv(file_path)
    return _format_table_section(frame)


def parse_excel(file_path: Path) -> str:
    """Excel dosyasındaki tüm sayfaları okur ve Markdown formatına dönüştürür."""
    workbook = pd.read_excel(file_path, sheet_name=None)
    sections: list[str] = []
    for sheet_name, frame in workbook.items():
        sections.append(f"Sheet: {sheet_name}\n{_format_table_section(frame)}")
    return "\n\n".join(sections)


def parse_pdf(file_path: Path) -> str:
    """PDF dosyasından metin ve tabloları çıkarır."""
    if PdfReader is None:
        raise RuntimeError("PDF desteği için pypdf paketi gereklidir.")

    reader = PdfReader(str(file_path))
    page_texts: list[str] = []
    for index, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").strip()
        page_texts.append(f"Page {index}\n{text}")
    return "\n\n".join(page_texts)


def parse_image_ocr(file_path: Path, provider: LLMProvider | None = None) -> str:
    """Görsel dosyasını OCR / Vision modeli ile analiz edip Markdown tablosu/metni çıkarır."""
    image_bytes = file_path.read_bytes()
    image_base64 = base64.b64encode(image_bytes).decode("utf-8")

    # 1. Verilen provider'da ocr metodu varsa kullan
    if provider and hasattr(provider, "ocr") and callable(provider.ocr):
        try:
            return provider.ocr(image_base64)
        except Exception as exc:
            logger.warning(f"Belirtilen provider OCR hatası: {exc}")

    # 2. KloudeksProvider (Qwen-OCR) dene
    if os.getenv("MIA_API_KEY"):
        try:
            return KloudeksProvider().ocr(image_base64)
        except Exception as exc:
            logger.warning(f"Kloudeks OCR hatası: {exc}")

    # 3. Nvidia Vision dene
    if os.getenv("NVIDIA_API_KEY"):
        try:
            return NvidiaProvider().ocr(image_base64)
        except Exception as exc:
            logger.warning(f"Nvidia Vision OCR hatası: {exc}")

    # 4. Fallback: OCR modellerine ulaşılamadıysa dosya bilgisini dön
    return f"[Görsel: {file_path.name} yüklendi. Görsel OCR servisi yanıt vermedi; kullanıcı açıklamasıyla değerlendirilecek.]"


def parse_uploaded_file(
    file_path: Path,
    original_filename: str,
    provider: LLMProvider | None = None,
) -> dict[str, Any]:
    """Yüklenen dosyanın uzantısına göre uygun ayrıştırıcıyı çağırır ve sonuç döndürür."""
    suffix = Path(original_filename).suffix.lower()

    try:
        if suffix == ".csv":
            content = parse_csv(file_path)
            return {
                "success": True,
                "filename": original_filename,
                "content_type": "csv",
                "markdown_content": content,
                "metadata": {"file_type": "csv"},
            }
        elif suffix in {".xlsx", ".xls"}:
            content = parse_excel(file_path)
            return {
                "success": True,
                "filename": original_filename,
                "content_type": "excel",
                "markdown_content": content,
                "metadata": {"file_type": "excel"},
            }
        elif suffix in {".png", ".jpg", ".jpeg", ".webp"}:
            content = parse_image_ocr(file_path, provider=provider)
            return {
                "success": True,
                "filename": original_filename,
                "content_type": "image",
                "markdown_content": content,
                "metadata": {"file_type": "image"},
            }
        elif suffix == ".pdf":
            content = parse_pdf(file_path)
            return {
                "success": True,
                "filename": original_filename,
                "content_type": "pdf",
                "markdown_content": content,
                "metadata": {"file_type": "pdf"},
            }
        else:
            return {
                "success": False,
                "filename": original_filename,
                "content_type": "unknown",
                "markdown_content": "",
                "error": f"Desteklenmeyen dosya türü: {suffix}. Desteklenen türler: .xlsx, .xls, .csv, .pdf, .png, .jpg, .jpeg, .webp",
            }
    except Exception as exc:
        return {
            "success": False,
            "filename": original_filename,
            "content_type": "error",
            "markdown_content": "",
            "error": f"Dosya ayrıştırma hatası: {str(exc)}",
        }
