"""Pytest fixtures for EVDS module tests."""
import json
from pathlib import Path
import pytest
import yaml

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def mock_manifest_path():
    """Path to the valid mock manifest YAML file."""
    return FIXTURES_DIR / "mock_series_manifest.yaml"


@pytest.fixture
def mock_invalid_manifest_path():
    """Path to an invalid/incomplete mock manifest YAML file."""
    return FIXTURES_DIR / "mock_invalid_manifest.yaml"


@pytest.fixture
def mock_evds_raw_response():
    """Sample raw EVDS dictionary response payload."""
    with open(FIXTURES_DIR / "mock_evds_response.json", "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def temp_bronze_dir(tmp_path):
    """Provides a temporary bronze directory structure: data/bronze/evds."""
    bronze_dir = tmp_path / "data" / "bronze" / "evds"
    bronze_dir.mkdir(parents=True, exist_ok=True)
    return bronze_dir


@pytest.fixture
def mock_catalog_data():
    """Sample raw category, subcategory, and series catalog JSON payload."""
    with open(FIXTURES_DIR / "mock_catalog_data.json", "r", encoding="utf-8") as f:
        return json.load(f)

