"""EVDS Client and API Key Rotation unit tests.

Serves Acceptance Criteria Scenarios:
- Scenario 3: [Error Case / Edge Case] Rate Limit asildiginda anahtar rotasyonu (BR-05)
"""
import os
from unittest.mock import MagicMock, patch
import pytest
import requests

from app.modules.evds.client import EvdsClient


class TestEvdsClientKeyRotation:
    """Tests for EvdsClient key rotation and rate limit handling."""

    @pytest.fixture(autouse=True)
    def setup_env_keys(self, monkeypatch):
        """Sets up 4 mock EVDS API keys in environment."""
        monkeypatch.setenv("EVDS_API_KEY_1", "KEY_1_TEST")
        monkeypatch.setenv("EVDS_API_KEY_2", "KEY_2_TEST")
        monkeypatch.setenv("EVDS_API_KEY_3", "KEY_3_TEST")
        monkeypatch.setenv("EVDS_API_KEY_4", "KEY_4_TEST")

    def test_client_loads_configured_keys_from_environment(self):
        """Verify client initializes with all available EVDS_API_KEY_n keys."""
        client = EvdsClient()
        assert len(client.api_keys) >= 4
        assert client.api_keys[:4] == [
            "KEY_1_TEST",
            "KEY_2_TEST",
            "KEY_3_TEST",
            "KEY_4_TEST",
        ]

    @patch("app.modules.evds.client.evdsAPI")
    def test_key_rotation_on_http_429_rate_limit(
        self, mock_evds_api_cls, mock_evds_raw_response
    ):
        """Scenario 3: HTTP 429 alindiginda siradaki anahtara gecis (BR-05).

        First call (KEY_1) -> HTTP 429
        Second call (KEY_2) -> HTTP 429
        Third call (KEY_3) -> Success (mock_evds_raw_response)
        """
        # Create 429 HTTPError simulation
        response_429 = requests.Response()
        response_429.status_code = 429
        error_429 = requests.exceptions.HTTPError("429 Client Error: Too Many Requests", response=response_429)

        # Mock instances created per key
        instance_key1 = MagicMock()
        instance_key1.get_data.side_effect = error_429

        instance_key2 = MagicMock()
        instance_key2.get_data.side_effect = error_429

        instance_key3 = MagicMock()
        instance_key3.get_data.return_value = mock_evds_raw_response

        # mock_evds_api_cls will return these instances in order
        mock_evds_api_cls.side_effect = [instance_key1, instance_key2, instance_key3]

        client = EvdsClient()
        result = client.get_data(
            series_code="TP.KTF10",
            start_date="01-01-2021",
            end_date="01-06-2026",
            raw=True,
        )

        # Verify operation succeeded without crashing
        assert result == mock_evds_raw_response

        # Verify 3 EVDS instances were initialized with rotated keys
        assert mock_evds_api_cls.call_count == 3
        mock_evds_api_cls.assert_any_call(key="KEY_1_TEST")
        mock_evds_api_cls.assert_any_call(key="KEY_2_TEST")
        mock_evds_api_cls.assert_any_call(key="KEY_3_TEST")

    @patch("app.modules.evds.client.evdsAPI")
    def test_all_keys_exhausted_raises_exception(self, mock_evds_api_cls):
        """When all available keys return HTTP 429, client raises an exception."""
        response_429 = requests.Response()
        response_429.status_code = 429
        error_429 = requests.exceptions.HTTPError("429 Client Error", response=response_429)

        mock_instance = MagicMock()
        mock_instance.get_data.side_effect = error_429
        mock_evds_api_cls.return_value = mock_instance

        client = EvdsClient()

        with pytest.raises(Exception) as exc_info:
            client.get_data(
                series_code="TP.KTF10",
                start_date="01-01-2021",
                end_date="01-06-2026",
                raw=True,
            )

        assert "429" in str(exc_info.value) or "exhausted" in str(exc_info.value).lower() or "rate limit" in str(exc_info.value).lower()

    @patch("app.modules.evds.client.evdsAPI")
    def test_get_data_paginates_when_1000_limit_hit(self, mock_evds_api_cls):
        """When EVDS returns exactly 1000 items, client automatically fetches earlier pages."""
        from datetime import datetime, timedelta
        base1 = datetime(2024, 1, 1)
        chunk1 = [{"Tarih": (base1 + timedelta(days=i)).strftime("%d-%m-%Y"), "val": float(i)} for i in range(1000)]

        base2 = datetime(2021, 1, 1)
        chunk2 = [{"Tarih": (base2 + timedelta(days=i)).strftime("%d-%m-%Y"), "val": float(i)} for i in range(500)]

        mock_instance = MagicMock()
        mock_instance.get_data.side_effect = [chunk1, chunk2]
        mock_evds_api_cls.return_value = mock_instance

        client = EvdsClient()
        result = client.get_data(
            series_code="TP.DK.USD.A.YTL",
            start_date="01-01-2021",
            end_date="01-06-2026",
            raw=True,
        )

        assert len(result) == 1500
        assert mock_instance.get_data.call_count == 2

