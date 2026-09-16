import base64
from pathlib import Path
import pandas as pd
import pytest
from unittest.mock import MagicMock, patch

from backend.app.services.attachment_parser import (
    parse_csv,
    parse_excel,
    parse_pdf,
    parse_image_ocr,
    parse_uploaded_file,
)


def test_parse_csv_comma_delimited(tmp_path: Path):
    csv_file = tmp_path / "sample.csv"
    csv_file.write_text("Tarih,Enflasyon,Faiz\n2024-01,64.8,45.0\n2024-02,67.1,45.0\n", encoding="utf-8")
    
    result = parse_csv(csv_file)
    assert "| Tarih | Enflasyon | Faiz |" in result
    assert "2024-01" in result
    assert "64.8" in result
    assert "row_count: 2" in result


def test_parse_csv_semicolon_delimited(tmp_path: Path):
    csv_file = tmp_path / "semicolon.csv"
    csv_file.write_text("Sektor;Kredi_Tutari;Takip_Orani\nTarim;150000;2.4\nSanayi;450000;1.8\n", encoding="utf-8")
    
    result = parse_csv(csv_file)
    assert "| Sektor | Kredi_Tutari | Takip_Orani |" in result
    assert "Tarim" in result
    assert "150000" in result
    assert "row_count: 2" in result


def test_parse_excel_multi_sheet(tmp_path: Path):
    excel_file = tmp_path / "financials.xlsx"
    with pd.ExcelWriter(excel_file) as writer:
        df1 = pd.DataFrame({"Yil": [2023, 2024], "Kar": [100, 150]})
        df2 = pd.DataFrame({"Kalem": ["Varliklar", "Yukumlulukler"], "Tutar": [500, 300]})
        df1.to_excel(writer, sheet_name="Gelir_Tablosu", index=False)
        df2.to_excel(writer, sheet_name="Bilanco", index=False)

    result = parse_excel(excel_file)
    assert "Sheet: Gelir_Tablosu" in result
    assert "Sheet: Bilanco" in result
    assert "| Yil | Kar |" in result
    assert "Varliklar" in result


def test_parse_pdf_extracts_pages(tmp_path: Path):
    pdf_file = tmp_path / "dummy.pdf"
    pdf_file.write_bytes(b"%PDF-1.4 dummy pdf content")

    mock_page_1 = MagicMock()
    mock_page_1.extract_text.return_value = "TCMB Para Politikası Raporu\nFaiz kararı %50 seviyesinde sabit tutuldu."
    mock_reader = MagicMock()
    mock_reader.pages = [mock_page_1]

    with patch("backend.app.services.attachment_parser.PdfReader", return_value=mock_reader):
        result = parse_pdf(pdf_file)
        assert "Page 1" in result
        assert "TCMB Para Politikası Raporu" in result
        assert "50" in result


def test_parse_image_ocr_with_provider(tmp_path: Path):
    img_file = tmp_path / "test.png"
    img_file.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR...")

    mock_provider = MagicMock()
    mock_provider.ocr.return_value = "| Banka | Mevduat Faizi |\n| Akbank | %48.5 |"

    result = parse_image_ocr(img_file, provider=mock_provider)
    assert "| Banka | Mevduat Faizi |" in result
    assert mock_provider.ocr.called


def test_parse_uploaded_file_routes_correctly(tmp_path: Path):
    # CSV
    csv_file = tmp_path / "data.csv"
    csv_file.write_text("A,B\n1,2\n", encoding="utf-8")
    parsed_csv = parse_uploaded_file(csv_file, "original_data.csv")
    assert parsed_csv["success"] is True
    assert parsed_csv["content_type"] == "csv"
    assert "| A | B |" in parsed_csv["markdown_content"]

    # Excel
    xlsx_file = tmp_path / "data.xlsx"
    pd.DataFrame({"X": [10, 20]}).to_excel(xlsx_file, index=False)
    parsed_xlsx = parse_uploaded_file(xlsx_file, "data.xlsx")
    assert parsed_xlsx["success"] is True
    assert parsed_xlsx["content_type"] == "excel"
    assert "Sheet: Sheet1" in parsed_xlsx["markdown_content"]

    # Image
    png_file = tmp_path / "chart.png"
    png_file.write_bytes(b"\x89PNG\r\n\x1a\n")
    mock_provider = MagicMock()
    mock_provider.ocr.return_value = "Enflasyon Grafiği 2024"
    parsed_png = parse_uploaded_file(png_file, "chart.png", provider=mock_provider)
    assert parsed_png["success"] is True
    assert parsed_png["content_type"] == "image"
    assert "Enflasyon Grafiği 2024" in parsed_png["markdown_content"]

    # Unsupported format
    unsupported_file = tmp_path / "archive.zip"
    unsupported_file.write_bytes(b"PK\x03\x04")
    parsed_unsupported = parse_uploaded_file(unsupported_file, "archive.zip")
    assert parsed_unsupported["success"] is False
    assert "Desteklenmeyen dosya türü" in parsed_unsupported["error"]
