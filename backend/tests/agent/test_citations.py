from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from backend.app.agent.loop import run_agent
from backend.app.agent.tool_registry import ToolRegistry
from backend.app.tools.base import BaseTool
from pydantic import BaseModel


class DummyWebSearchTool(BaseTool):
    name = "web_search"
    description = "Mock web search"

    class Input(BaseModel):
        query: str

    class Output(BaseModel):
        success: bool = True
        results: list[dict[str, Any]] = []

    def run(self, params: Input) -> Output:
        return self.Output(
            success=True,
            results=[
                {
                    "title": "TÜİK Enflasyon Bülteni",
                    "url": "https://www.tuik.gov.tr/bulten/123",
                    "snippet": "Enflasyon açıklandı.",
                },
                {
                    "title": "TCMB Duyuru",
                    "url": "https://www.tcmb.gov.tr/duyuru/456",
                    "snippet": "Faiz kararı.",
                },
            ],
        )


class DummyWebUrlReaderTool(BaseTool):
    name = "web_url_reader"
    description = "Mock web url reader"

    class Input(BaseModel):
        url: str
        render_js: bool = False

    class Output(BaseModel):
        success: bool = True
        url: str
        title: str | None = "Borsa İstanbul Verileri"
        content: str = "BIST 100 verisi"

    def run(self, params: Input) -> Output:
        return self.Output(
            success=True,
            url=params.url,
            title="Borsa İstanbul Verileri",
            content="BIST 100 verisi",
        )


class DummyLakehouseTool(BaseTool):
    name = "lakehouse_query"
    description = "Mock lakehouse tool"

    class Input(BaseModel):
        sql: str

    class Output(BaseModel):
        success: bool = True
        data: list[dict[str, Any]] = []

    def run(self, params: Input) -> Output:
        return self.Output(success=True, data=[{"col": 1}])


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: str


@dataclass
class MockChatResponse:
    content: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)


class SequenceProvider:
    def __init__(self, responses: list[MockChatResponse]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def chat(self, messages: list[dict], tools: list[dict] | None = None) -> MockChatResponse:
        self.calls.append({"messages": messages, "tools": tools})
        if self.responses:
            return self.responses.pop(0)
        return MockChatResponse(content="Default response", tool_calls=[])


def test_agent_system_prompt_requires_citations_for_web_tools():
    provider = SequenceProvider([MockChatResponse(content="Tamam", tool_calls=[])])
    run_agent("Enflasyon nedir?", registry=ToolRegistry(), provider=provider, max_iterations=1)

    system_prompt = provider.calls[0]["messages"][0]["content"]
    assert "### 🔗 Kaynaklar" in system_prompt
    assert "web_search" in system_prompt
    assert "web_url_reader" in system_prompt


def test_citation_added_by_llm_preserved():
    registry = ToolRegistry()
    registry.register(DummyWebSearchTool())

    llm_answer_with_citations = (
        "2026 yılı enflasyon verileri açıklandı.\n\n"
        "### 🔗 Kaynaklar\n"
        "- [TÜİK Resmi Sitesi](https://www.tuik.gov.tr/bulten/123) - Resmi enflasyon bülteni"
    )

    responses = [
        MockChatResponse(
            content=None,
            tool_calls=[
                ToolCall(
                    id="call_1",
                    name="web_search",
                    arguments=json.dumps({"query": "2026 enflasyon"}),
                )
            ],
        ),
        MockChatResponse(content=llm_answer_with_citations, tool_calls=[]),
    ]

    provider = SequenceProvider(responses)
    final_output = run_agent(
        "2026 enflasyon nedir?",
        registry=registry,
        provider=provider,
        max_iterations=3,
    )

    # Should not duplicate the citation header
    assert final_output.count("### 🔗 Kaynaklar") == 1
    assert "https://www.tuik.gov.tr/bulten/123" in final_output


def test_citation_fallback_appended_when_missing():
    registry = ToolRegistry()
    registry.register(DummyWebSearchTool())

    llm_answer_without_citations = "2026 yılı enflasyonu %30 olarak gerçekleşti."

    responses = [
        MockChatResponse(
            content=None,
            tool_calls=[
                ToolCall(
                    id="call_1",
                    name="web_search",
                    arguments=json.dumps({"query": "2026 enflasyon"}),
                )
            ],
        ),
        MockChatResponse(content=llm_answer_without_citations, tool_calls=[]),
    ]

    provider = SequenceProvider(responses)
    final_output = run_agent(
        "2026 enflasyon nedir?",
        registry=registry,
        provider=provider,
        max_iterations=3,
    )

    # Post-processor should append the citation header and visited links
    assert "### 🔗 Kaynaklar" in final_output
    assert "[TÜİK Enflasyon Bülteni](https://www.tuik.gov.tr/bulten/123)" in final_output
    assert "[TCMB Duyuru](https://www.tcmb.gov.tr/duyuru/456)" in final_output
    assert final_output.startswith("2026 yılı enflasyonu %30 olarak gerçekleşti.")


def test_citation_fallback_for_web_url_reader():
    registry = ToolRegistry()
    registry.register(DummyWebUrlReaderTool())

    llm_answer_without_citations = "Borsa İstanbul verilerine göre endeks yükselişte."

    responses = [
        MockChatResponse(
            content=None,
            tool_calls=[
                ToolCall(
                    id="call_1",
                    name="web_url_reader",
                    arguments=json.dumps({"url": "https://www.borsaistanbul.com/veriler"}),
                )
            ],
        ),
        MockChatResponse(content=llm_answer_without_citations, tool_calls=[]),
    ]

    provider = SequenceProvider(responses)
    final_output = run_agent(
        "BIST verilerini oku",
        registry=registry,
        provider=provider,
        max_iterations=3,
    )

    assert "### 🔗 Kaynaklar" in final_output
    assert "[Borsa İstanbul Verileri](https://www.borsaistanbul.com/veriler)" in final_output


def test_citation_fallback_in_force_synthesis():
    registry = ToolRegistry()
    registry.register(DummyWebSearchTool())

    responses = [
        MockChatResponse(
            content=None,
            tool_calls=[
                ToolCall(
                    id="call_1",
                    name="web_search",
                    arguments=json.dumps({"query": "2026 enflasyon"}),
                )
            ],
        ),
        # Force synthesis response (max_iterations=1 hit after tool execution)
        MockChatResponse(content="Sentez sonucu: Enflasyon verisi alındı.", tool_calls=[]),
    ]

    provider = SequenceProvider(responses)
    final_output = run_agent(
        "2026 enflasyon nedir?",
        registry=registry,
        provider=provider,
        max_iterations=1,
    )

    assert "### 🔗 Kaynaklar" in final_output
    assert "https://www.tuik.gov.tr/bulten/123" in final_output


def test_no_citation_for_pure_lakehouse():
    registry = ToolRegistry()
    registry.register(DummyLakehouseTool())

    responses = [
        MockChatResponse(
            content=None,
            tool_calls=[
                ToolCall(
                    id="call_1",
                    name="lakehouse_query",
                    arguments=json.dumps({"sql": "SELECT 1"}),
                )
            ],
        ),
        MockChatResponse(content="Lakehouse sorgu sonucu: 1", tool_calls=[]),
    ]

    provider = SequenceProvider(responses)
    final_output = run_agent(
        "Konut kredisi faizi nedir?",
        registry=registry,
        provider=provider,
        max_iterations=3,
    )

    assert "### 🔗 Kaynaklar" not in final_output
    assert final_output == "Lakehouse sorgu sonucu: 1"
