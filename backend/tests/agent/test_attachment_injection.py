from unittest.mock import MagicMock
import pytest

from backend.app.agent.loop import run_agent
from backend.app.agent.tool_registry import ToolRegistry


class FakeResponse:
    def __init__(self, content="Dosyadaki veriler incelendi."):
        self.content = content
        self.tool_calls = []


def test_run_agent_injects_attachment_into_user_message():
    mock_provider = MagicMock()
    captured_messages = []

    def mock_chat(messages, tools=None):
        captured_messages.extend(messages)
        return FakeResponse()

    mock_provider.chat.side_effect = mock_chat

    run_agent(
        question="Görseldeki faiz oranını EVDS ile karşılaştır",
        registry=ToolRegistry(),
        provider=mock_provider,
        attachment_content="| Ay | Faiz |\n| 2024-01 | %45 |",
        attachment_name="faiz_tablosu.png",
    )

    user_msgs = [m for m in captured_messages if m.get("role") == "user"]
    assert len(user_msgs) > 0
    last_user_content = user_msgs[-1]["content"]

    assert "<attached_document filename='faiz_tablosu.png'" in last_user_content
    assert "| 2024-01 | %45 |" in last_user_content
    assert "Görseldeki faiz oranını EVDS ile karşılaştır" in last_user_content
