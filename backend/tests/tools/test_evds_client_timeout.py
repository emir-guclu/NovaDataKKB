from unittest.mock import MagicMock, patch

from backend.app.modules.evds.client import EVDS_REQUEST_TIMEOUT_SECONDS, EvdsClient


def test_evds_client_bounds_http_timeout():
    fake_api = MagicMock()
    original_get = MagicMock()
    fake_api.session.get = original_get

    with patch("backend.app.modules.evds.client.evdsAPI", return_value=fake_api) as cls:
        client = EvdsClient(api_keys=["test-key"])
        api = client._create_api_instance("test-key")

    cls.assert_called_once_with(key="test-key")

    api.session.get("https://example.com")

    original_get.assert_called_once_with(
        "https://example.com",
        timeout=EVDS_REQUEST_TIMEOUT_SECONDS,
    )
