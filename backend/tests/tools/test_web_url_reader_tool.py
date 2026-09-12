from __future__ import annotations

from pydantic import ValidationError
import pytest

from backend.app.agent.tool_registry import ToolRegistry
from backend.app.tools.web_url_reader import WebUrlReaderTool


class FakeExtractedContent:
    def __init__(
        self,
        *,
        success: bool = True,
        content_type: str = "html",
        title: str | None = "Baslik",
        text: str = "0123456789",
        metadata: dict | None = None,
        error: str | None = None,
    ) -> None:
        self.success = success
        self.content_type = content_type
        self.title = title
        self.text = text
        self.metadata = metadata or {}
        self.error = error


def test_web_url_reader_tool_schema_requires_url():
    tool = WebUrlReaderTool()

    with pytest.raises(ValidationError):
        tool.Input()


def test_web_url_reader_tool_runs_extractor_and_truncates(monkeypatch):
    def fake_extract(url, provider=None):
        assert url == "https://example.com/report"
        return FakeExtractedContent(text="abcdefghijklmnopqrstuvwxyz")

    monkeypatch.setattr("backend.app.tools.web_url_reader.extract_url_content", fake_extract)
    tool = WebUrlReaderTool()

    result = tool.run(tool.Input(url="https://example.com/report", max_length=10))

    assert result.success is True
    assert result.url == "https://example.com/report"
    assert result.content_type == "html"
    assert result.title == "Baslik"
    assert result.content == "abcdefghij"
    assert result.error is None


def test_web_url_reader_tool_returns_structured_failure(monkeypatch):
    def fake_extract(url, provider=None):
        return FakeExtractedContent(success=False, text="", error="indirilemedi")

    monkeypatch.setattr("backend.app.tools.web_url_reader.extract_url_content", fake_extract)
    tool = WebUrlReaderTool()

    result = tool.run(tool.Input(url="https://example.com/missing"))

    assert result.success is False
    assert result.content == ""
    assert result.error == "indirilemedi"


def test_web_url_reader_tool_can_be_registered():
    registry = ToolRegistry()
    registry.register(WebUrlReaderTool())

    schema = registry.to_openai_tools_format()

    assert registry.get("web_url_reader") is not None
    assert schema[0]["function"]["name"] == "web_url_reader"
    assert "url" in schema[0]["function"]["parameters"]["properties"]
