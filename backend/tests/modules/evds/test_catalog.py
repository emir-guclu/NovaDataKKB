"""EVDS Catalog discovery and parquet storage unit tests.

Serves Acceptance Criteria Scenarios:
- Scenario 5: [Happy Path] Keşif işlemi ile kataloğun başarıyla oluşturulması (BR-06)
- Scenario 6: [Happy Path] İndirme işlemi sonrasında kataloğun güncellenmesi (BR-06, BR-07, BR-10)
"""
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock
import pandas as pd
import pytest

from app.modules.evds.catalog import discover_all
from app.modules.evds.catalog_store import (
    load_catalog,
    save_catalog,
    update_series_status,
)
from app.modules.evds.client import EvdsClient


class TestCatalogDiscovery:
    """Tests for full discovery of EVDS categories, datagroups, and series (BR-06)."""

    def test_discover_all_creates_parquet_catalog(
        self, temp_bronze_dir, mock_catalog_data
    ):
        """Scenario 5: Keşif işlemi tüm kategorileri tarar ve parquet kataloğunu oluşturur (BR-06)."""
        catalog_path = temp_bronze_dir / "evds_catalog.parquet"

        # Mock EVDS client methods
        mock_client = MagicMock(spec=EvdsClient)
        mock_client.get_main_categories.return_value = mock_catalog_data["categories"]
        mock_client.get_sub_categories.side_effect = lambda cat_id: mock_catalog_data["sub_categories"].get(str(cat_id), [])
        mock_client.get_series.side_effect = lambda dg_code: mock_catalog_data["series"].get(dg_code, [])

        # Execute discovery
        df_result = discover_all(client=mock_client, output_path=catalog_path)

        # Verify parquet file was created on disk
        assert catalog_path.exists(), "Expected evds_catalog.parquet to be created on disk"
        assert catalog_path.stat().st_size > 0, "Parquet catalog file must not be empty"

        # Verify dataframe structure
        df_loaded = pd.read_parquet(catalog_path)
        assert len(df_loaded) == 2, "Expected 2 series in the catalog"

        # Verify required columns exist in schema
        required_columns = {
            "category_id",
            "category_name",
            "datagroup_id",
            "datagroup_name",
            "series_code",
            "series_name",
            "frequency",
            "is_ingested",
            "fetch_status",
            "last_ingested_at",
        }
        assert required_columns.issubset(set(df_loaded.columns)), (
            f"Missing required columns in catalog: {required_columns - set(df_loaded.columns)}"
        )

        # Verify initial default flags
        assert (df_loaded["is_ingested"] == False).all(), "All series must initially have is_ingested=False"
        assert "TP.KTF10" in df_loaded["series_code"].values
        assert "TP.FG.J0" in df_loaded["series_code"].values


class TestCatalogStore:
    """Tests for shared parquet catalog read/write/upsert operations (BR-07, BR-10)."""

    @pytest.fixture
    def initial_catalog_file(self, temp_bronze_dir):
        """Creates an initial catalog parquet file for store testing."""
        catalog_path = temp_bronze_dir / "evds_catalog.parquet"
        data = {
            "category_id": [1, 2],
            "category_name": ["Piyasa Verileri", "Fiyat Endeksleri"],
            "datagroup_id": ["bie_yssk", "bie_fe"],
            "datagroup_name": ["Menkul Kıymet İstatistikleri", "Tüketici Fiyat Endeksi"],
            "series_code": ["TP.KTF10", "TP.FG.J0"],
            "series_name": ["Konut Kredisi Faiz Oranı", "TÜFE Genel İndeksi"],
            "frequency": ["Haftalık", "Aylık"],
            "is_ingested": [False, False],
            "fetch_status": [None, None],
            "last_ingested_at": [None, None],
        }
        df = pd.DataFrame(data)
        df.to_parquet(catalog_path, index=False)
        return catalog_path

    def test_load_and_save_catalog(self, temp_bronze_dir):
        """Test round-trip save and load of catalog parquet."""
        catalog_path = temp_bronze_dir / "test_store.parquet"
        sample_df = pd.DataFrame({
            "series_code": ["TP.KTF10"],
            "is_ingested": [False],
            "fetch_status": ["PENDING"],
        })

        save_catalog(sample_df, catalog_path)
        assert catalog_path.exists()

        loaded_df = load_catalog(catalog_path)
        assert len(loaded_df) == 1
        assert loaded_df.iloc[0]["series_code"] == "TP.KTF10"
        assert loaded_df.iloc[0]["is_ingested"] == False

    def test_update_series_status_to_success(self, initial_catalog_file):
        """Scenario 6: Seri indirildikten sonra katalogda is_ingested=True ve fetch_status='SUCCESS' guncellenir (BR-07)."""
        # Update TP.KTF10
        updated = update_series_status(
            catalog_path=initial_catalog_file,
            series_code="TP.KTF10",
            is_ingested=True,
            fetch_status="SUCCESS",
        )
        assert updated is True, "Expected update_series_status to return True for existing series"

        # Verify disk parquet content
        df_updated = pd.read_parquet(initial_catalog_file)
        row_ktf10 = df_updated[df_updated["series_code"] == "TP.KTF10"].iloc[0]
        assert row_ktf10["is_ingested"] == True
        assert row_ktf10["fetch_status"] == "SUCCESS"
        assert pd.notna(row_ktf10["last_ingested_at"]), "last_ingested_at should be updated"

        # Verify other series is unmodified
        row_fg = df_updated[df_updated["series_code"] == "TP.FG.J0"].iloc[0]
        assert row_fg["is_ingested"] == False
        assert pd.isna(row_fg["fetch_status"]) or row_fg["fetch_status"] is None

    def test_update_non_existent_series_returns_false(self, initial_catalog_file):
        """Updating a series code that does not exist returns False and does not crash."""
        updated = update_series_status(
            catalog_path=initial_catalog_file,
            series_code="NON_EXISTING_SERIES",
            is_ingested=True,
            fetch_status="SUCCESS",
        )
        assert updated is False
