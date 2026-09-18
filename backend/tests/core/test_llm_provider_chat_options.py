from types import SimpleNamespace

import pytest

from backend.app.core.llm_provider import DeepSeekProvider, KloudeksProvider, NvidiaProvider


class FakeCompletions:
    def __init__(self) -> None:
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        message = SimpleNamespace(content="{}", tool_calls=None)
        choice = SimpleNamespace(message=message, finish_reason="stop")
        return SimpleNamespace(choices=[choice])


class FakeClient:
    def __init__(self) -> None:
        self.completions = FakeCompletions()
        self.chat = SimpleNamespace(completions=self.completions)


@pytest.mark.parametrize("provider_cls", [KloudeksProvider, NvidiaProvider, DeepSeekProvider])
def test_chat_passes_temperature_and_response_format(provider_cls):
    client = FakeClient()
    provider = provider_cls(client=client)

    response = provider.chat(
        [{"role": "user", "content": "json don"}],
        temperature=0.0,
        response_format={"type": "json_object"},
    )

    assert response.content == "{}"
    assert client.completions.kwargs["temperature"] == 0.0
    assert client.completions.kwargs["response_format"] == {"type": "json_object"}
