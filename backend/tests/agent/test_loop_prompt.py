from __future__ import annotations

from backend.app.agent.loop import run_agent
from backend.app.agent.tool_registry import ToolRegistry


class FakeResponse:
    content = "Tamam"
    tool_calls = []


class CapturingProvider:
    def __init__(self) -> None:
        self.messages = None
        self.tools = None

    def chat(self, messages, tools=None):
        self.messages = messages
        self.tools = tools
        return FakeResponse()


def test_agent_system_prompt_forbids_url_guessing_and_mentions_followup_assets():
    provider = CapturingProvider()

    result = run_agent(
        "Bu sayfadaki raporu oku",
        registry=ToolRegistry(),
        provider=provider,
        max_iterations=1,
    )

    assert result == "Tamam"
    system_prompt = provider.messages[0]["content"]
    assert "URL tahmin ederek uydurma" in system_prompt
    assert "Bulunan Dosyalar" in system_prompt
    assert "Gorseller" in system_prompt
    assert "ikinci adimda" in system_prompt
    assert "render_js=True" in system_prompt
