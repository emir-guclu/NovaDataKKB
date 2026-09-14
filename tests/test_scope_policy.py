import pytest
from unittest.mock import MagicMock

from backend.app.agent.loop import run_agent
from backend.app.agent.tool_registry import ToolRegistry


class CapturingProvider:
    def __init__(self, response_generator=None) -> None:
        self.messages = None
        self.tools = None
        self.response_generator = response_generator

    def chat(self, messages, tools=None):
        self.messages = messages
        self.tools = tools
        if self.response_generator:
            return self.response_generator(messages, tools)
        mock_resp = MagicMock()
        mock_resp.content = "Mock response"
        mock_resp.tool_calls = []
        return mock_resp


def test_scope_policy_in_system_prompt():
    provider = CapturingProvider()
    run_agent("Herhangi bir soru", ToolRegistry(), provider, max_iterations=1)

    system_prompt = provider.messages[0]["content"]
    assert "KKB'nin (Kredi Kayıt Bürosu) finansal veri analiz asistanısın" in system_prompt
    assert "BDDK, EVDS, FinTürk" in system_prompt
    assert "hava durumu, genel sohbet, kod yazma" in system_prompt
    assert "kapsamının dışında olduğunu belirt ve ne tür sorular sorabileceğine dair 2-3 örnek ver" in system_prompt
    assert "web_search tool'unu kullanabilirsin" in system_prompt


def test_scope_policy_unrelated_query_no_tools_called():
    # Tamamen alakasız soru senaryosu: "Bana bir şiir yaz"
    # LLM tool çağırmadan kapsam dışı uyarısı ve örnekler dönmeli
    def unrelated_llm_response(messages, tools):
        resp = MagicMock()
        resp.content = (
            "Ben KKB finansal veri analiz asistanıyım. Şiir yazma talebiniz kapsamım dışındadır. "
            "Bunun yerine şu tür sorular sorabilirsiniz: \n"
            "1. Konut kredisi faiz oranları son 6 ayda nasıl değişti?\n"
            "2. BDDK verilerine göre takipteki kredi oranı nedir?"
        )
        resp.tool_calls = []
        return resp

    provider = CapturingProvider(response_generator=unrelated_llm_response)
    result = run_agent(
        "Bana bir şiir yaz",
        ToolRegistry(),
        provider,
        max_iterations=2,
    )

    assert "kapsamım dışındadır" in result.lower() or "kapsamı" in result.lower()
    assert "konut kredisi" in result.lower() or "bddk" in result.lower()


def test_scope_policy_borderline_query_calls_web_search():
    # Sınırda soru senaryosu: "Türkiye'de son ekonomi haberleri neler?"
    call_log = []

    def borderline_llm_response(messages, tools):
        resp = MagicMock()
        if not call_log:
            tool_call = MagicMock()
            tool_call.id = "call_1"
            tool_call.name = "web_search"
            tool_call.arguments = '{"query": "Türkiye son ekonomi haberleri"}'
            resp.tool_calls = [tool_call]
            resp.content = None
            call_log.append("tool_called")
        else:
            resp.tool_calls = []
            resp.content = "Son ekonomi haberlerine göre enflasyon ve büyüme verileri açıklandı."
        return resp

    provider = CapturingProvider(response_generator=borderline_llm_response)
    result = run_agent(
        "Türkiye'de son ekonomi haberleri neler?",
        ToolRegistry(),
        provider,
        max_iterations=2,
    )

    assert "tool_called" in call_log
    assert "Son ekonomi haberlerine göre" in result


def test_scope_policy_in_scope_query_calls_financial_tools():
    # Net kapsam içi senaryo: "Konut kredisi hacmi geçen aya göre nasıl değişti?"
    call_log = []

    def in_scope_llm_response(messages, tools):
        resp = MagicMock()
        if not call_log:
            tool_call = MagicMock()
            tool_call.id = "call_1"
            tool_call.name = "series_catalog_search"
            tool_call.arguments = '{"query": "konut kredisi hacmi"}'
            resp.tool_calls = [tool_call]
            resp.content = None
            call_log.append("financial_tool_called")
        else:
            resp.tool_calls = []
            resp.content = "Konut kredisi hacmi geçen aya göre %2.4 artmıştır."
        return resp

    provider = CapturingProvider(response_generator=in_scope_llm_response)
    result = run_agent(
        "Konut kredisi hacmi geçen aya göre nasıl değişti?",
        ToolRegistry(),
        provider,
        max_iterations=2,
    )

    assert "financial_tool_called" in call_log
    assert "Konut kredisi hacmi geçen aya göre" in result
