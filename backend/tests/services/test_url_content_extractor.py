from __future__ import annotations

from io import BytesIO

import pandas as pd
import pytest
import requests

from backend.app.services import url_content_extractor as extractor


class FakeResponse:
    def __init__(
        self,
        body: bytes,
        *,
        content_type: str,
        url: str = "https://example.com/report",
        headers: dict[str, str] | None = None,
        status_code: int = 200,
    ) -> None:
        self.body = body
        self.url = url
        self.headers = {"Content-Type": content_type, **(headers or {})}
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            error = requests.HTTPError(f"{self.status_code} Error")
            error.response = self
            raise error
        return None

    def iter_content(self, chunk_size: int = 8192):
        for index in range(0, len(self.body), chunk_size):
            yield self.body[index : index + chunk_size]


class FakeProvider:
    def __init__(self) -> None:
        self.seen_image_base64: str | None = None

    def ocr(self, image_base64: str) -> str:
        self.seen_image_base64 = image_base64
        return "OCR ile okunan tablo metni"


def mock_get(monkeypatch, response: FakeResponse) -> None:
    def fake_get(url, *, headers, stream, timeout):
        assert headers["User-Agent"].startswith("Mozilla/5.0")
        assert "application/pdf" in headers["Accept"]
        assert "tr-TR" in headers["Accept-Language"]
        assert stream is True
        assert timeout == 15
        return response

    monkeypatch.setattr(extractor.requests, "get", fake_get)


def test_extract_url_content_cleans_html_to_markdown(monkeypatch):
    html = b"""
    <html>
      <head><title>Finans Raporu</title><style>.x{}</style></head>
      <body>
        <nav>menu</nav>
        <h1>Konut Kredisi</h1>
        <p>Faiz oranlari yuksek seyrediyor.</p>
        <script>alert(1)</script>
        <footer>alt bilgi</footer>
      </body>
    </html>
    """
    mock_get(monkeypatch, FakeResponse(html, content_type="text/html; charset=utf-8"))

    result = extractor.extract_url_content("https://example.com/report.html")

    assert result.success is True
    assert result.content_type == "html"
    assert result.title == "Finans Raporu"
    assert "Konut Kredisi" in result.text
    assert "Faiz oranlari yuksek seyrediyor." in result.text
    assert "menu" not in result.text
    assert "alert" not in result.text
    assert "Dinamik icerik uyarisi" not in result.text


def test_extract_url_content_lists_absolute_document_and_image_urls(monkeypatch):
    html = b"""
    <html>
      <head><title>BIST</title></head>
      <body>
        <main>
          <h1>Piyasa Verileri</h1>
          <a href="/dosyalar/kmtp/veriler/kmp_au.pdf">Altin Islemleri</a>
          <a href="rapor.xlsx">Excel Raporu</a>
          <img src="/file/inline-images/teknoloji_gorsel.jpeg" alt="BISTECH mimari semasi">
          <img src="/logo.png" alt="Logo">
        </main>
      </body>
    </html>
    """
    mock_get(
        monkeypatch,
        FakeResponse(
            html,
            content_type="text/html; charset=utf-8",
            url="https://www.borsaistanbul.com/veriler/piyasa-verileri",
        ),
    )

    result = extractor.extract_url_content("https://www.borsaistanbul.com/veriler/piyasa-verileri")

    assert result.success is True
    assert "Bulunan Dosyalar" in result.text
    assert "Altin Islemleri: https://www.borsaistanbul.com/dosyalar/kmtp/veriler/kmp_au.pdf" in result.text
    assert "Excel Raporu: https://www.borsaistanbul.com/veriler/rapor.xlsx" in result.text
    assert "Sayfa Ici Gorseller / Semalar" in result.text
    assert "BISTECH mimari semasi: https://www.borsaistanbul.com/file/inline-images/teknoloji_gorsel.jpeg" in result.text
    assert "logo.png" not in result.text


def test_extract_url_content_uses_browser_fallback_after_forbidden_static_fetch(monkeypatch):
    calls: list[str] = []

    def fake_get(url, *, headers, stream, timeout):
        calls.append("static")
        return FakeResponse(
            b"Forbidden",
            content_type="text/html",
            url=url,
            status_code=403,
        )

    def fake_browser_fetch(url):
        calls.append("browser")
        return (
            b"<html><head><title>Rendered</title></head><body><div>JS ile gelen veri</div></body></html>",
            "text/html; charset=utf-8",
            url,
            None,
        )

    monkeypatch.setattr(extractor.requests, "get", fake_get)
    monkeypatch.setattr(extractor, "_fetch_with_browser", fake_browser_fetch, raising=False)

    result = extractor.extract_url_content("https://example.com/spa")

    assert result.success is True
    assert result.title == "Rendered"
    assert "JS ile gelen veri" in result.text
    assert calls == ["static", "browser"]


def test_extract_url_content_reports_missing_browser_for_empty_js_shell(monkeypatch):
    html = b"<html><body><div id=\"root\"></div><script src=\"app.js\"></script></body></html>"
    mock_get(monkeypatch, FakeResponse(html, content_type="text/html", url="https://example.com/app"))

    def fake_browser_fetch(url):
        return None, "", url, "Playwright kurulu degil"

    monkeypatch.setattr(extractor, "_fetch_with_browser", fake_browser_fetch, raising=False)

    result = extractor.extract_url_content("https://example.com/app")

    assert result.success is True
    assert "Dinamik icerik uyarisi: Playwright kurulu degil" in result.text


def test_extract_url_content_formats_csv_preview_and_statistics(monkeypatch):
    csv_bytes = b"date,value,name\n2026-01-01,10,A\n2026-02-01,20,B\n"
    mock_get(monkeypatch, FakeResponse(csv_bytes, content_type="text/csv"))

    result = extractor.extract_url_content("https://example.com/data.csv")

    assert result.success is True
    assert result.content_type == "csv"
    assert "| date" in result.text
    assert "row_count: 2" in result.text
    assert "value" in result.text
    assert "mean" in result.text


def test_extract_url_content_lists_excel_sheets(monkeypatch):
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        pd.DataFrame({"date": ["2026-01-01"], "value": [42]}).to_excel(
            writer,
            index=False,
            sheet_name="Sheet A",
        )
    mock_get(
        monkeypatch,
        FakeResponse(
            output.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ),
    )

    result = extractor.extract_url_content("https://example.com/book.xlsx")

    assert result.success is True
    assert result.content_type == "excel"
    assert result.metadata["sheets"] == ["Sheet A"]
    assert "Sheet: Sheet A" in result.text
    assert "| date" in result.text


def test_extract_url_content_uses_ocr_for_images(monkeypatch):
    provider = FakeProvider()
    mock_get(monkeypatch, FakeResponse(b"image-bytes", content_type="image/png"))

    result = extractor.extract_url_content("https://example.com/chart.png", provider=provider)

    assert result.success is True
    assert result.content_type == "image"
    assert result.text == "OCR ile okunan tablo metni"
    assert provider.seen_image_base64 is not None


def test_extract_url_content_reads_pdf_pages(monkeypatch):
    class FakePage:
        def __init__(self, text: str) -> None:
            self._text = text

        def extract_text(self) -> str:
            return self._text

    class FakePdfReader:
        def __init__(self, stream) -> None:
            assert stream.read() == b"%PDF fake"
            self.pages = [FakePage("Birinci sayfa"), FakePage("Ikinci sayfa")]

    monkeypatch.setattr(extractor, "PdfReader", FakePdfReader)
    mock_get(monkeypatch, FakeResponse(b"%PDF fake", content_type="application/pdf"))

    result = extractor.extract_url_content("https://example.com/file.pdf")

    assert result.success is True
    assert result.content_type == "pdf"
    assert "Page 1" in result.text
    assert "Birinci sayfa" in result.text
    assert result.metadata["page_count"] == 2


def test_extract_url_content_rejects_oversized_content(monkeypatch):
    body = b"x" * (extractor.MAX_BYTES + 1)
    mock_get(monkeypatch, FakeResponse(body, content_type="text/plain"))

    result = extractor.extract_url_content("https://example.com/huge.txt")

    assert result.success is False
    assert "15 MB" in result.error
