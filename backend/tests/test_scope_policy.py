"""Tests for Scope Policy (Kapsam Dışı Soru Politikası)."""
from __future__ import annotations

from unittest.mock import MagicMock

from backend.app.agent.loop import run_agent
from backend.app.agent.tool_registry import ToolRegistry
from backend.app.core.llm_provider import LLMResponse, LLMToolCall
from backend.app.tools.change_detection import ChangeDetectionTool
from backend.app.tools.series_catalog_search import SeriesCatalogSearchTool
from backend.app.tools.web_search import WebSearchTool


def test_scope_policy_completely_out_of_domain_calls_no_tools():
    """Tamamen alakasız soru (örn: şiir yaz): Tool çağırmadan doğrudan kapsam dışı mesajı dönmeli."""
    mock_provider = MagicMock()
    # LLM tool çağırmadan doğrudan kapsam dışı yanıt üretiyor
    mock_provider.chat.return_value = LLMResponse(
        content=(
            "Ben KKB'nin finansal veri analiz asistanıyım. Şiir yazma veya genel sohbet gibi "
            "finans dışı konular kapsamımın dışındadır. Size şu konularda yardımcı olabilirim:\n"
            "- Konut kredisi faiz oranlarındaki değişimler\n"
            "- BDDK tüketici kredileri ve kart bakiyeleri\n"
            "- TCMB resmi rezervleri ve enflasyon verileri"
        ),
        tool_calls=[],
        finish_reason="stop",
        raw=None,
    )

    registry = ToolRegistry()
    registry.register(WebSearchTool())
    registry.register(SeriesCatalogSearchTool())

    executed_tools = []

    def on_event(event_type: str, data: dict):
        if event_type == "llm_decision":
            executed_tools.append(data.get("tool_name"))

    result = run_agent(
        question="Bana bir şiir yaz",
        registry=registry,
        provider=mock_provider,
        on_event=on_event,
    )

    # Hiçbir tool çağrılmamalı
    assert len(executed_tools) == 0
    assert "finans" in result.lower() or "kapsam" in result.lower()
    assert "KKB" in result


def test_scope_policy_borderline_question_can_use_web_search():
    """Sınırda soru (örn: genel ekonomi/finans haberleri): web_search çağrılabilmeli."""
    mock_provider = MagicMock()
    # 1. adımda web_search çağırır, 2. adımda yanıt döner
    mock_provider.chat.side_effect = [
        LLMResponse(
            content="",
            tool_calls=[
                LLMToolCall(
                    id="call_web_1",
                    name="web_search",
                    arguments='{"query": "Turkiye son ekonomi haberleri"}',
                )
            ],
            finish_reason="tool_calls",
            raw=None,
        ),
        LLMResponse(
            content="Son ekonomi haberlerine göre enflasyon gerilemektedir.\n\n### 🔗 Kaynaklar\n- [Haber](https://news.com)",
            tool_calls=[],
            finish_reason="stop",
            raw=None,
        ),
    ]

    registry = ToolRegistry()
    mock_web = MagicMock(spec=WebSearchTool)
    mock_web.name = "web_search"
    mock_web.description = "Web search"
    mock_web.Input = WebSearchTool.Input
    mock_web.run.return_value = WebSearchTool.Output(
        success=True,
        results=[{"title": "Ekonomi Haber", "url": "https://news.com", "snippet": "Haber detayı"}],
    )
    registry.register(mock_web)

    executed_tools = []

    def on_event(event_type: str, data: dict):
        if event_type == "llm_decision":
            executed_tools.append(data.get("tool_name"))

    result = run_agent(
        question="Türkiye'de son ekonomi haberleri neler?",
        registry=registry,
        provider=mock_provider,
        on_event=on_event,
    )

    assert "web_search" in executed_tools
    assert "🔗 Kaynaklar" in result


def test_scope_policy_in_domain_financial_uses_local_tools():
    """Net kapsam içi finansal soru: yerel araçları (series_catalog_search / change_detection) kullanmalı."""
    mock_provider = MagicMock()
    mock_provider.chat.side_effect = [
        LLMResponse(
            content="",
            tool_calls=[
                LLMToolCall(
                    id="call_cat_1",
                    name="series_catalog_search",
                    arguments='{"query": "konut kredisi hacmi"}',
                )
            ],
            finish_reason="tool_calls",
            raw=None,
        ),
        LLMResponse(
            content="Konut kredisi hacmi geçen aya göre %1.5 arttı.",
            tool_calls=[],
            finish_reason="stop",
            raw=None,
        ),
    ]

    registry = ToolRegistry()
    mock_cat = MagicMock(spec=SeriesCatalogSearchTool)
    mock_cat.name = "series_catalog_search"
    mock_cat.description = "Catalog search"
    mock_cat.Input = SeriesCatalogSearchTool.Input
    mock_cat.run.return_value = SeriesCatalogSearchTool.Output(
        success=True,
        query="konut kredisi hacmi",
        found_in_lakehouse=True,
        matches=[
            {
                "series_id": "BDDK_MONTHLY:tuketici_kredileri:tuketici_kredileri_konut",
                "series_code": "konut",
                "series_name": "Konut",
                "source": "BDDK",
                "category": "kredi",
                "unit": "TL",
                "freq": "M",
                "date_range": "2021-2026",
                "similarity_score": 0.85,
                "recommended_tool": "change_detection",
            }
        ],
    )
    registry.register(mock_cat)

    executed_tools = []

    def on_event(event_type: str, data: dict):
        if event_type == "llm_decision":
            executed_tools.append(data.get("tool_name"))

    result = run_agent(
        question="Konut kredisi hacmi geçen aya göre nasıl değişti?",
        registry=registry,
        provider=mock_provider,
        on_event=on_event,
    )

    assert "series_catalog_search" in executed_tools
    assert "Konut kredisi" in result
