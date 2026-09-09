"""Ingestion and idempotency behavior tests for EVDS Bronze layer.

Serves Acceptance Criteria Scenarios:
- Scenario 1: [Happy Path] First download writes all series raw JSON files (BR-01, BR-02, BR-03, BR-06, BR-07, BR-08)
- Scenario 2: [Boundary/Edge Case] Idempotency skips already downloaded series (BR-04)
- Scenario 4: [Error Case] Invalid manifest format raises error (BR-02)
"""
import json
import logging
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from app.modules.evds.ingestion import ingest_series
from app.modules.evds.client import EvdsClient


class TestEvdsIngestion:
    """Tests for EVDS Bronze Ingestion workflow and idempotency."""

    def test_happy_path_all_series_downloaded_as_raw_json(
        self, mock_manifest_path, temp_bronze_dir, mock_evds_raw_response
    ):
        """Scenario 1: Happy Path - Dizin bosken manifestteki seriler basariyla indirilir.

        Verifies BR-01, BR-02, BR-03, BR-07, BR-08.
        """
        mock_client = MagicMock(spec=EvdsClient)
        mock_client.get_data.return_value = mock_evds_raw_response

        # Execute ingestion
        result = ingest_series(
            manifest_path=mock_manifest_path,
            output_dir=temp_bronze_dir,
            client=mock_client,
        )

        expected_series = [
            "TP.KTF10",
            "TP.FG.J0",
            "TP.HKFE01",
            "TP.DK.USD.A.YTL",
        ]

        # Verify all 4 files were created
        for code in expected_series:
            target_file = temp_bronze_dir / f"{code}.json"
            assert target_file.exists(), f"Expected {code}.json to exist in {temp_bronze_dir}"
            assert target_file.stat().st_size > 0, f"{code}.json must not be empty"

            # Verify content is valid JSON matching raw mock
            with open(target_file, "r", encoding="utf-8") as f:
                saved_data = json.load(f)
            assert saved_data == mock_evds_raw_response

        # Verify client was called with raw=True for each series
        assert mock_client.get_data.call_count == len(expected_series)
        for code in expected_series:
            mock_client.get_data.assert_any_call(
                series_code=code,
                start_date="01-01-2021",
                end_date="01-06-2026",
                raw=True,
            )

    def test_idempotency_skips_existing_non_empty_files(
        self, mock_manifest_path, temp_bronze_dir, mock_evds_raw_response, caplog
    ):
        """Scenario 2: Idempotency - Daha once indirilmis dolu dosyalar atlanir (BR-04)."""
        # Pre-create TP.KTF10.json with some data
        pre_existing_file = temp_bronze_dir / "TP.KTF10.json"
        pre_existing_content = {"existing": "data"}
        with open(pre_existing_file, "w", encoding="utf-8") as f:
            json.dump(pre_existing_content, f)

        mock_client = MagicMock(spec=EvdsClient)
        mock_client.get_data.return_value = mock_evds_raw_response

        with caplog.at_level(logging.INFO):
            ingest_series(
                manifest_path=mock_manifest_path,
                output_dir=temp_bronze_dir,
                client=mock_client,
            )

        # Verify client was NOT called for TP.KTF10
        called_series = [
            call.kwargs.get("series_code") or call.args[0]
            for call in mock_client.get_data.call_args_list
        ]
        assert "TP.KTF10" not in called_series, "TP.KTF10 should have been skipped and not fetched via API"

        # Verify [SKIP] logged for TP.KTF10
        assert any("[SKIP]" in record.message and "TP.KTF10" in record.message for record in caplog.records), (
            "Expected [SKIP] log message for TP.KTF10"
        )

        # Verify existing file was not overwritten
        with open(pre_existing_file, "r", encoding="utf-8") as f:
            assert json.load(f) == pre_existing_content

        # Other 3 series should have been downloaded
        for code in ["TP.FG.J0", "TP.HKFE01", "TP.DK.USD.A.YTL"]:
            assert (temp_bronze_dir / f"{code}.json").exists()

    def test_invalid_manifest_raises_exception_and_does_not_save(
        self, mock_invalid_manifest_path, temp_bronze_dir
    ):
        """Scenario 4: Error Case - Gecersiz manifest dosyasinda hata firlatilir (BR-02)."""
        mock_client = MagicMock(spec=EvdsClient)

        with pytest.raises((ValueError, KeyError, Exception)):
            ingest_series(
                manifest_path=mock_invalid_manifest_path,
                output_dir=temp_bronze_dir,
                client=mock_client,
            )

        # Ensure no series files are saved in bronze dir
        saved_files = list(temp_bronze_dir.glob("*.json"))
        assert len(saved_files) == 0, "No files should be written on invalid manifest"

    def test_ingestion_updates_catalog_store_on_successful_download(
        self, mock_manifest_path, temp_bronze_dir, mock_evds_raw_response
    ):
        """Scenario 6: İndirme işlemi sonrasında katalog güncellenir (BR-06, BR-07)."""
        mock_client = MagicMock(spec=EvdsClient)
        mock_client.get_data.return_value = mock_evds_raw_response

        with patch("app.modules.evds.ingestion.update_series_status") as mock_update_status:
            ingest_series(
                manifest_path=mock_manifest_path,
                output_dir=temp_bronze_dir,
                client=mock_client,
            )

            # Verify update_series_status was called for downloaded series
            expected_series = ["TP.KTF10", "TP.FG.J0", "TP.HKFE01", "TP.DK.USD.A.YTL"]
            assert mock_update_status.call_count == len(expected_series)
            for code in expected_series:
                mock_update_status.assert_any_call(
                    catalog_path=temp_bronze_dir / "evds_catalog.parquet",
                    series_code=code,
                    is_ingested=True,
                    fetch_status="SUCCESS",
                )

    def test_failed_ingestion_marks_catalog_as_failed(
        self, mock_manifest_path, temp_bronze_dir
    ):
        """Scenario 8: API hata verdiğinde serinin başarısız sayılması ve katalogda FAILED işaretlenmesi (BR-12, AC-8)."""
        mock_client = MagicMock(spec=EvdsClient)
        # Simulate API failure returning None or raising RuntimeError
        mock_client.get_data.side_effect = RuntimeError("EVDS API returned None for series.")

        with patch("app.modules.evds.ingestion.update_series_status") as mock_update_status:
            stats = ingest_series(
                manifest_path=mock_manifest_path,
                output_dir=temp_bronze_dir,
                client=mock_client,
            )

            # Assert failure counters
            assert stats["total"] == 4
            assert stats["fetched"] == 0
            assert stats["failed"] == 4

            # Verify update_series_status was called with FAILED and is_ingested=False for all 4 series
            expected_series = ["TP.KTF10", "TP.FG.J0", "TP.HKFE01", "TP.DK.USD.A.YTL"]
            assert mock_update_status.call_count == len(expected_series)
            for code in expected_series:
                mock_update_status.assert_any_call(
                    catalog_path=temp_bronze_dir / "evds_catalog.parquet",
                    series_code=code,
                    is_ingested=False,
                    fetch_status="FAILED",
                )

