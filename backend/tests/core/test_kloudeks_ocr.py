import base64
import os
from pathlib import Path
import pytest
from dotenv import load_dotenv
from app.core.llm_provider import KloudeksProvider

load_dotenv()
pytestmark = pytest.mark.skipif(not os.getenv("MIA_API_KEY"), reason="MIA_API_KEY not configured")


def test_kloudeks_ocr_extracts_known_text():
    fixture = Path("backend/tests/fixtures/ocr_sample.png")
    image_base64 = base64.b64encode(fixture.read_bytes()).decode("utf-8")
    text = KloudeksProvider().ocr(image_base64)
    assert "NOVA FINANSAL RAPOR" in text
    assert "125 Milyar TL" in text
    assert "%3.4" in text
