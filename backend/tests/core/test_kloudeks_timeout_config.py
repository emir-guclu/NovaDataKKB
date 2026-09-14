from unittest.mock import patch

from backend.app.core.llm_provider import KloudeksProvider


def test_kloudeks_provider_has_bounded_network_timeout():
    with patch("backend.app.core.llm_provider.OpenAI") as mock_openai:
        KloudeksProvider(api_key="test-key")

    mock_openai.assert_called_once_with(
        api_key="test-key",
        base_url=KloudeksProvider.BASE_URL,
        timeout=60.0,
        max_retries=0,
    )
