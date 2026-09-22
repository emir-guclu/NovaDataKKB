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


def test_kloudeks_provider_default_and_custom_model():
    client = FakeClient()
    provider = KloudeksProvider(client=client)
    assert provider.model == "deepseek-ai/DeepSeek-V4.1-Flash"

    provider_qwen = KloudeksProvider(client=client, model=KloudeksProvider.MODEL_QWEN)
    assert provider_qwen.model == "kkbhackathon2026/Qwen3.8-27B"

    provider_qwen.chat([{"role": "user", "content": "test"}])
    assert client.completions.kwargs["model"] == "kkbhackathon2026/Qwen3.8-27B"


def test_get_default_provider_kloudeks_flash_and_qwen():
    from backend.app.core.llm_provider import get_default_provider

    p_flash = get_default_provider("kloudeks-deepseek-flash")
    assert isinstance(p_flash, KloudeksProvider)
    assert p_flash.model == "deepseek-ai/DeepSeek-V4.1-Flash"

    p_qwen = get_default_provider("kloudeks-qwen")
    assert isinstance(p_qwen, KloudeksProvider)
    assert p_qwen.model == "kkbhackathon2026/Qwen3.8-27B"

