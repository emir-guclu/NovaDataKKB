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


def test_parse_csv_text_only_no_numeric_columns(tmp_path: Path):
    """Sayısal sütun içermeyen CSV dosyasında 'No objects to concatenate' hatası verilmemelidir."""
    csv_file = tmp_path / "text_only.csv"
    csv_file.write_text("Sektor,Bolge,Durum\nTarim,Ege,Aktif\nSanayi,Marmara,Pasif\n", encoding="utf-8")

    result = parse_csv(csv_file)
    assert "| Sektor | Bolge | Durum |" in result
    assert "Tarim" in result
    assert "row_count: 2" in result
    # Sayısal istatistik olmamalı ama çökmemelidir
    assert "statistics:" not in result


def test_parse_csv_with_leading_metadata_lines(tmp_path: Path):
    """Borsa İstanbul ve kurumlardan indirilen metadata satırlı CSV doğru başlık ve satır sayısıyla okunmalıdır."""
    csv_content = (
        "Dışa Aktarım Tarihi: 23.09.2026\n"
        "Toplam Kayıt Sayısı: 2\n"
        "\n"
        "Hisse Kodu;Şirket Adı;Sektör;Fiyat\n"
        "THYAO;Türk Hava Yolları;Havacılık;320,50\n"
        "GARAN;Garanti BBVA;Bankacılık;115,20\n"
    )
    csv_file = tmp_path / "bist_export.csv"
    csv_file.write_text(csv_content, encoding="utf-8")

    result = parse_csv(csv_file)
    assert "| Hisse Kodu | Şirket Adı | Sektör | Fiyat |" in result
    assert "THYAO" in result
    assert "Türk Hava Yolları" in result
    assert "row_count: 2" in result


def test_parse_csv_turkish_numeric_formats(tmp_path: Path):
    """Türkçe sayı formatları (18.107.041.090,70 veya '1.200.000,50') sayısal değere dönüştürülmeli ve istatistik üretilmelidir."""
    csv_content = (
        "Sirket;Piyasa_Degeri;Gunluk_Hacim\n"
        "THYAO;18.107.041.090,70;1.200.000,50\n"
        "GARAN;25.000.000.000,00;3.500.000,00\n"
    )
    csv_file = tmp_path / "turkish_numbers.csv"
    csv_file.write_text(csv_content, encoding="utf-8")

    result = parse_csv(csv_file)
    assert "row_count: 2" in result
    assert "statistics:" in result
    assert "Piyasa_Degeri" in result
    assert "Gunluk_Hacim" in result


def test_parse_csv_utf8_bom(tmp_path: Path):
    """UTF-8 BOM (\ufeff) içeren CSV dosyaları sorunsuz okunmalıdır."""
    csv_content = "\ufeffKod,Ad,Tutar\nAKBNK,Akbank,150.5\nISCTR,İş Bankası,200.0\n"
    csv_file = tmp_path / "bom_data.csv"
    csv_file.write_text(csv_content, encoding="utf-8-sig")

    result = parse_csv(csv_file)
    assert "| Kod | Ad | Tutar |" in result
    assert "\ufeff" not in result
    assert "row_count: 2" in result


def test_parse_excel_with_empty_sheets_and_metadata(tmp_path: Path):
    """Boş sayfalar ve başta boşluk/metadata içeren Excel sayfaları güvenle işlenmelidir."""
    excel_file = tmp_path / "complex_sheets.xlsx"
    with pd.ExcelWriter(excel_file) as writer:
        # Boş sayfa
        empty_df = pd.DataFrame()
        empty_df.to_excel(writer, sheet_name="Bos_Sekme", index=False)

        # Başında boş satır ve metadata olan sayfa
        messy_df = pd.DataFrame([
            ["Rapor Adı: Sektör Analizi", None, None],
            [None, None, None],
            ["Sektor", "Kredi", "Takip"],
            ["Tarim", "1.500.000,50", "2,4"],
            ["Sanayi", "4.500.000,00", "1,8"],
        ])
        messy_df.to_excel(writer, sheet_name="Veri_Sekmesi", header=False, index=False)

    result = parse_excel(excel_file)
    assert "Sheet: Veri_Sekmesi" in result
    assert "Tarim" in result
    assert "Sanayi" in result


def test_parse_excel_tefas_export_with_title_and_unnamed_columns(tmp_path: Path):
    """TEFAS Excel çıktılarında ilk satırda başlık, 2. satırda tarih olduğunda Unnamed: 1/2/3 yerine asıl başlıklar bulunmalıdır."""
    excel_file = tmp_path / "tefas_export.xlsx"
    with pd.ExcelWriter(excel_file) as writer:
        df = pd.DataFrame([
            ["TEFAS - Tarihsel Veriler", None, None, None],
            ["Rapor Tarihi: 23.09.2026", None, None, None],
            ["Tarih", "Fon Kodu", "Fon Adı", "Fiyat"],
            ["2026-09-20", "TCD", "Tacirler Portföy Değişken Fon", "15,45"],
            ["2026-09-21", "TCD", "Tacirler Portföy Değişken Fon", "15,60"],
            ["2026-09-22", "TCD", "Tacirler Portföy Değişken Fon", "15,80"],
        ])
        df.to_excel(writer, sheet_name="TEFAS_Veri", header=False, index=False)

    result = parse_excel(excel_file)
    assert "Unnamed:" not in result
    assert "columns: Tarih, Fon Kodu, Fon Adı, Fiyat" in result
    assert "row_count: 3" in result



def test_parse_csv_tefas_export_with_title_and_metadata(tmp_path: Path):
    """TEFAS CSV çıktılarında ilk satırda başlık, sonraki satırlarda metadata olduğunda kolon başlıkları korunmalıdır."""
    csv_content = (
        "TEFAS Fon Karşılaştırma Raporu\n"
        "İndirme Zamanı: 23.09.2026 14:30\n"
        "\n"
        "Fon Kodu;Fon Unvanı;Fiyat;Getiri (%)\n"
        "TCD;Tacirler Değişken Fon;15,45;2,35\n"
        "AFT;Ak Portföy Yeni Teknolojiler;42,10;1,80\n"
    )
    csv_file = tmp_path / "tefas_fonlar.csv"
    csv_file.write_text(csv_content, encoding="utf-8")

    result = parse_csv(csv_file)
    assert "Unnamed:" not in result
    assert "| Fon Kodu | Fon Unvanı | Fiyat | Getiri (%) |" in result
    assert "TCD" in result
    assert "AFT" in result
    assert "row_count: 2" in result


def test_parse_uploaded_file_docx_support(tmp_path: Path):
    """Word (.docx) dosyaları MarkItDown ile başarıyla ayrıştırılmalıdır."""
    docx_file = tmp_path / "rapor.docx"
    # Dummy docx or text file simulation
    docx_file.write_text("TCMB Enflasyon Değerlendirmesi ve Politika Notu", encoding="utf-8")
    
    parsed = parse_uploaded_file(docx_file, "rapor.docx")
    assert parsed["success"] is True
    assert parsed["content_type"] == "document"


def test_parse_csv_headerless_numeric_data_does_not_promote_numbers_as_headers(tmp_path: Path):
    """Başlıksız sayısal CSV verisinde sayısal değerler (18107041090,70 vb.) kolon adı yapılmamalı, veri satırı olarak korunmalıdır."""
    csv_content = (
        "2021-01;18107041090,70;905352054,54;3434067109,63\n"
        "2021-02;19000000000,00;910000000,00;3500000000,00\n"
    )
    csv_file = tmp_path / "headerless.csv"
    csv_file.write_text(csv_content, encoding="utf-8")

    result = parse_csv(csv_file)
    assert "row_count: 2" in result
    # Sayısal değer kolon ismi olmamalı, tabloda yer almalı
    assert "columns: 18107041090" not in result
    assert "2021-01" in result
    assert "18107041090" in result


def test_parse_csv_61_rows_full_display(tmp_path: Path):
    """61 satırlık dosya 25 satırda kesilmemeli, tüm 61 satır tam olarak gösterilmelidir."""
    lines = ["Tarih;Hacim"]
    for year in range(2021, 2026):
        for month in range(1, 13):
            lines.append(f"{year}-{month:02d};{1000 + month * 10}")
    # 60 ay + 1 ay = 61 satır
    lines.append("2026-01;2000")
    
    csv_file = tmp_path / "sixty_one_rows.csv"
    csv_file.write_text("\n".join(lines), encoding="utf-8")

    result = parse_csv(csv_file)
    assert "row_count: 61" in result
    assert "2021-01" in result
def test_parse_csv_with_quoted_comma_decimals_and_headers(tmp_path: Path):
    """Tırnak içinde ondalık virgülü olan CSV dosyalarında başlık satırının atlanmadığı ve kolon isimlerinin korunduğu doğrulanmalıdır."""
    csv_content = (
        "Dışa Aktarım Tarihi:,23.09.2026 12:33:03\n"
        "Toplam Kayıt Sayısı:,61\n"
        "\n"
        "Dönem,Toplam İşlem Hacmi (TL),Günlük Ortalama İşlem Hacmi (TL),Net Takas Tutarı (TL)\n"
        '2021-01,"18107041090,70","905352054,54","3434067109,63"\n'
        '2021-02,"15632911085,07","781645554,25","4088786011,32"\n'
    )
    csv_file = tmp_path / "bist_quoted_commas.csv"
    csv_file.write_text(csv_content, encoding="utf-8")

    result = parse_csv(csv_file)
    assert "Sutun_2" not in result
    assert "columns: Dönem, Toplam İşlem Hacmi (TL), Günlük Ortalama İşlem Hacmi (TL), Net Takas Tutarı (TL)" in result
    assert "row_count: 2" in result
    assert "| 2021-01 | 18107041090.7 | 905352054.54 | 3434067109.63 |" in result or "18107041090" in result



