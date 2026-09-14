import os

import pytest
from pydantic import ValidationError

import backend.app.tools.web_search as web_search_module
from backend.app.tools.web_search import WebSearchTool


class FakeDDGS:
    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def text(self, query, max_results=3):
        assert query == "TCMB faiz karari"
        assert max_results == 3
        return [
            {
                "title": "TCMB Faiz Kararı",
                "href": "https://example.com/tcmb",
                "body": "TCMB faiz kararına ilişkin arama sonucu.",
            }
        ]


def test_web_search_success(monkeypatch):
    monkeypatch.setattr(web_search_module, "DDGS", FakeDDGS)

    tool = WebSearchTool()
    result = tool.run(tool.Input(query="TCMB faiz karari"))

    assert result.success is True
    assert result.error is None
    assert len(result.results) == 1
    assert result.results[0]["title"] == "TCMB Faiz Kararı"
    assert result.results[0]["url"] == "https://example.com/tcmb"


def test_web_search_error_case():
    tool = WebSearchTool()
    result = tool.run(tool.Input(query="ERROR_TRIGGER"))

    assert result.success is False
    assert result.error is not None


def test_web_search_validation_error():
    tool = WebSearchTool()

    with pytest.raises(ValidationError):
        tool.Input()


@pytest.mark.skipif(
    os.getenv("RUN_LIVE_WEB_TESTS") != "1",
    reason="live web test is opt-in",
)
def test_web_search_live():
    tool = WebSearchTool()
    result = tool.run(tool.Input(query="Türkiye enflasyon TÜİK 2026"))

    assert result.success is True
    assert result.results
