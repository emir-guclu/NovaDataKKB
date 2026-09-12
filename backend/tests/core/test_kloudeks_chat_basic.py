import os
import pytest
from dotenv import load_dotenv
from app.core.llm_provider import KloudeksProvider

load_dotenv()
pytestmark = pytest.mark.skipif(not os.getenv("MIA_API_KEY"), reason="MIA_API_KEY not configured")


def test_kloudeks_chat_basic():
    provider = KloudeksProvider()
    response = provider.chat([{"role": "user", "content": "Sadece OK yaz."}])
    assert response.finish_reason == "stop"
    assert response.content
    assert "OK" in response.content.upper()
