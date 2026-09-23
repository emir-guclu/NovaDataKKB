from __future__ import annotations

import base64
import csv
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

try:
    from markitdown import MarkItDown
    _markitdown_converter = MarkItDown()
except ImportError:  # pragma: no cover
    MarkItDown = None
    _markitdown_converter = None

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


def _convert_to_numeric_if_possible(series: pd.Series) -> pd.Series:
    """Türkçe sayı formatlarını (18.107.041.090,70 veya '1.200,50' veya '150,5') ve standart sayıları float/int'e dönüştürür."""
    if pd.api.types.is_numeric_dtype(series):
        return series

    try:
        s = series.astype(str).str.strip().str.strip('"\'')
        has_comma = s.str.contains(",", regex=False).any()
        has_dot = s.str.contains(".", regex=False).any()

        # Türkçe format: virgül içeren sayılar
        if has_comma:
            if has_dot:
                # 18.107.041.090,70 -> 18107041090.70
                s_clean = s.str.replace(".", "", regex=False).str.replace(",", ".", regex=False)
            else:
                # 150,5 -> 150.5
                s_clean = s.str.replace(",", ".", regex=False)
            converted = pd.to_numeric(s_clean, errors="coerce")
            non_null_original = series.dropna().shape[0]
            non_null_converted = converted.dropna().shape[0]
            if non_null_original > 0 and (non_null_converted / non_null_original) >= 0.6:
                return converted
    except Exception:
        pass

    # Standart sayısal dönüşüm (örn: 64.8, -45.0, 150000)
    try:
        converted = pd.to_numeric(series, errors="coerce")
        non_null_original = series.dropna().shape[0]
        non_null_converted = converted.dropna().shape[0]
        if non_null_original > 0 and (non_null_converted / non_null_original) >= 0.6:
            return converted
    except Exception:
        pass

    return series


def _is_numeric_cell(val: Any) -> bool:
    """Hücrenin net sayısal bir veri (float/int/para) olup olmadığını kontrol eder."""
    if pd.isna(val):
        return False
    s_val = str(val).strip().strip('"\'')
    if not s_val:
        return False
    # Tarih formatları (2021-01, 2021-01-01, 01.01.2021) sayısal değer sayılmaz
    if len(s_val) in (7, 8, 10) and any(sep in s_val for sep in ("-", "/", ".")):
        parts = s_val.replace("/", "-").replace(".", "-").split("-")
        if len(parts) in (2, 3) and all(p.isdigit() for p in parts):
            return False

    try:
        s_clean = s_val.replace(".", "").replace(",", ".")
        float(s_clean)
        return True
    except Exception:
        return False


def _detect_and_promote_header(frame: pd.DataFrame) -> pd.DataFrame:
    """Tablodaki başlık öncesi metadata/başlık satırlarını veya 'Unnamed:' kolonlarını temizleyip gerçek başlığı bulur."""
    if frame.empty:
        return frame

    # Tamamen boş satır ve sütunları temizle
    frame = frame.dropna(how="all").dropna(axis=1, how="all")
    if frame.empty:
        return frame

    cols_str = [str(c).strip() for c in frame.columns]
    unnamed_count = sum(1 for c in cols_str if c.startswith("Unnamed:") or c.isdigit() or c == "" or c.startswith("Col_") or c.startswith("Sutun_"))
    total_cols = len(cols_str)

    # Eğer 1 veya daha fazla 'Unnamed:' varsa veya sütun isimleri sayılardan ibaretse
    needs_header_search = (unnamed_count > 0 and (unnamed_count >= total_cols * 0.3 or total_cols <= 3 or unnamed_count >= 1))

    if needs_header_search and len(frame) > 0:
        best_header_idx = None
        best_score = -1

        # İlk 15 satırı tara
        max_search = min(15, len(frame))
        for idx in range(max_search):
            row = frame.iloc[idx]
            non_empty = [val for val in row if pd.notna(val) and str(val).strip() != ""]
            non_empty_count = len(non_empty)

            if non_empty_count < 2 and total_cols > 1:
                continue

            numeric_count = sum(1 for val in non_empty if _is_numeric_cell(val))
            text_count = non_empty_count - numeric_count

            # Sadece hücrelerin ÇOĞUNLUĞU (%70'ten fazlası) net sayısal veri ise bu satır veri satırıdır, başlık olamaz
            if non_empty_count > 1 and (numeric_count / non_empty_count) >= 0.7:
                continue

            score = (non_empty_count * 3) + (text_count * 4) - (numeric_count * 2)
            if score > best_score and non_empty_count >= (total_cols * 0.4 if total_cols > 2 else 1):
                best_score = score
                best_header_idx = idx

        if best_header_idx is not None:
            raw_header = frame.iloc[best_header_idx]
            new_columns = []
            for i, val in enumerate(raw_header):
                val_str = str(val).strip() if pd.notna(val) else ""
                if val_str:
                    new_columns.append(val_str)
                else:
                    new_columns.append(f"Sutun_{i+1}")

            frame = frame.iloc[best_header_idx + 1:].copy()
            frame.columns = new_columns
        else:
            # Hiçbir metin başlık satırı bulunamadıysa (dosya tamamen başlıksız ham veri ise):
            # Asla veri satırını silme veya kolon ismi yapma! Kolon isimlerini temiz varsayılan yap:
            new_columns = []
            for i in range(total_cols):
                col_sample = str(frame.iloc[0, i]).strip() if len(frame) > 0 else ""
                if i == 0 and (len(col_sample) in (7, 10) and ("-" in col_sample or "." in col_sample or "/" in col_sample)):
                    new_columns.append("Donem_Tarih")
                else:
                    new_columns.append(f"Sutun_{i+1}")
            frame.columns = new_columns

    # Kolon isimlerindeki temizlik
    cleaned_columns = []
    for i, col in enumerate(frame.columns):
        col_name = str(col).replace("\ufeff", "").strip()
        if not col_name or col_name.startswith("Unnamed:"):
            col_name = f"Sutun_{i+1}"
        cleaned_columns.append(col_name)
    frame.columns = cleaned_columns

    frame = frame.dropna(how="all")
    return frame


def _clean_dataframe(frame: pd.DataFrame) -> pd.DataFrame:
    """BOM karakterlerini, Unnamed başlıkları, boş satır/sütunları ve Türkçe sayısal alanları temizler."""
    if frame.empty:
        return frame

    # Başlık tespiti ve Unnamed kolonların düzeltilmesi
    frame = _detect_and_promote_header(frame)
    if frame.empty:
        return frame

    # Sayısal alan dönüşümü
    for col in frame.columns:
        frame[col] = _convert_to_numeric_if_possible(frame[col])

    return frame


def _format_table_section(frame: pd.DataFrame) -> str:
    frame = _clean_dataframe(frame)
    if frame.empty or len(frame.columns) == 0:
        return "row_count: 0\ncolumns: \n\n| (Boş Tablo) |\n| --- |\n| Veri bulunamadı |"

    # Tablo satırlarını göster: 1000 satıra kadar tüm satırları eksiksiz gösteriyoruz
    if len(frame) <= 1000:
        table_md = _to_markdown(frame)
    else:
        head_part = _to_markdown(frame.head(60))
        tail_part = _to_markdown(frame.tail(20))
        table_md = f"{head_part}\n\n*... (Toplam {len(frame)} satırdan ilk 60 ve son 20 satır gösterilmektedir) ...*\n\n{tail_part}"

    parts = [
        f"row_count: {len(frame)}",
        "columns: " + ", ".join(str(column) for column in frame.columns),
        table_md,
    ]

    numeric_cols = frame.select_dtypes(include="number")
    if not numeric_cols.empty and len(numeric_cols.columns) > 0 and len(frame) > 0:
        try:
            numeric_summary = numeric_cols.agg(["min", "max", "mean"])
            if not numeric_summary.empty and len(numeric_summary.columns) > 0:
                parts.append("statistics:\n" + _to_markdown(numeric_summary.reset_index(names="metric")))
        except Exception:
            pass

    return "\n\n".join(parts)


def parse_csv(file_path: Path) -> str:
    """CSV dosyasını dinamik ayraç tespiti, metadata atlama ve akıllı başlık algılama ile okur."""
    raw_text = None
    for enc in ("utf-8-sig", "utf-8", "windows-1254", "iso-8859-9", "latin-1"):
        try:
            raw_text = file_path.read_text(encoding=enc)
            break
        except Exception:
            continue

    if raw_text is None:
        raw_text = file_path.read_text(encoding="utf-8", errors="ignore")

    lines = [line for line in raw_text.splitlines() if line.strip()]
    candidates = [";", ",", "\t", "|"]
    best_frame = None
    best_score = -1

    for sep in candidates:
        if not lines:
            continue

        # Satırları csv.reader ile ayrıştırarak gerçek sütun sayısını buluyoruz.
        # Böylece tırnak içindeki ondalık virgülleri (örn. "18107041090,70") ayraç gibi sayılmaz.
        field_counts: list[int] = []
        for line in lines[:30]:
            try:
                row = next(csv.reader([line], delimiter=sep))
                non_empty = [c for c in row if c.strip()]
                field_counts.append(len(non_empty) if non_empty else len(row))
            except Exception:
                field_counts.append(line.count(sep) + 1)

        max_fields = max(field_counts) if field_counts else 0
        if max_fields <= 1:
            continue

        # Tablonun başladığı satır: max_fields sütun sayısına ulaşan İLK satır (başlık satırı)
        start_idx = 0
        for idx, cnt in enumerate(field_counts):
            if cnt == max_fields:
                start_idx = idx
                break

        table_text = "\n".join(lines[start_idx:])
        try:
            frame = pd.read_csv(
                StringIO(table_text),
                sep=sep,
                header=None,
                engine="python",
                on_bad_lines="skip",
                dtype=str,
            )
            cleaned = _clean_dataframe(frame)
            if not cleaned.empty:
                col_weight = 100 if len(cleaned.columns) > 1 else 1
                score = (len(cleaned.columns) * col_weight) + len(cleaned)
                if score > best_score:
                    best_score = score
                    best_frame = cleaned
        except Exception:
            continue

    if best_frame is None or best_frame.empty:
        try:
            frame = pd.read_csv(file_path, header=None, on_bad_lines="skip", dtype=str)
            best_frame = _clean_dataframe(frame)
        except Exception:
            best_frame = pd.DataFrame()

    return _format_table_section(best_frame)


def parse_excel(file_path: Path) -> str:
    """Excel dosyasındaki tüm sayfaları akıllı başlık ve sayı algılama ile okur."""
    try:
        workbook = pd.read_excel(file_path, sheet_name=None, header=None)
    except Exception:
        workbook = pd.read_excel(file_path, sheet_name=None)

    sections: list[str] = []
    for sheet_name, raw_frame in workbook.items():
        cleaned_frame = _clean_dataframe(raw_frame)
        if cleaned_frame.empty or len(cleaned_frame.columns) == 0:
            continue
        sections.append(f"Sheet: {sheet_name}\n{_format_table_section(cleaned_frame)}")

    if not sections:
        return "Excel dosyasında dolu veri sayfası bulunamadı."
    return "\n\n".join(sections)


def parse_pdf(file_path: Path) -> str:
    """PDF dosyasından metin ve sayfaları pypdf (veya MarkItDown fallback) ile çıkarır."""
    if PdfReader is not None:
        try:
            reader = PdfReader(str(file_path))
            page_texts: list[str] = []
            for index, page in enumerate(reader.pages, start=1):
                text = (page.extract_text() or "").strip()
                page_texts.append(f"Page {index}\n{text}")
            return "\n\n".join(page_texts)
        except Exception as exc:
            logger.warning(f"pypdf ayrıştırma hatası: {exc}, MarkItDown deneniyor.")

    if _markitdown_converter is not None:
        try:
            res = _markitdown_converter.convert(str(file_path))
            if res and res.text_content and res.text_content.strip():
                return res.text_content.strip()
        except Exception as exc:
            logger.warning(f"MarkItDown PDF hatası: {exc}")

    raise RuntimeError("PDF desteği için pypdf veya markitdown paketi gereklidir.")


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
        elif suffix in {".docx", ".doc", ".pptx", ".ppt"}:
            if _markitdown_converter is not None:
                res = _markitdown_converter.convert(str(file_path))
                content = res.text_content.strip() if res and res.text_content else ""
            else:
                content = f"[{original_filename} yüklendi]"
            return {
                "success": True,
                "filename": original_filename,
                "content_type": "document",
                "markdown_content": content,
                "metadata": {"file_type": suffix.lstrip(".")},
            }
        else:
            return {
                "success": False,
                "filename": original_filename,
                "content_type": "unknown",
                "markdown_content": "",
                "error": f"Desteklenmeyen dosya türü: {suffix}. Desteklenen türler: .xlsx, .xls, .csv, .pdf, .docx, .pptx, .png, .jpg, .jpeg, .webp",
            }
    except Exception as exc:
        return {
            "success": False,
            "filename": original_filename,
            "content_type": "error",
            "markdown_content": "",
            "error": f"Dosya ayrıştırma hatası: {str(exc)}",
        }
