"""Unit and idempotency tests for EVDS metadata ingestion module (metadata.py)."""

import json
from pathlib import Path
import pytest

from app.modules.evds.metadata import (
    clean_text,
    load_manifest_series,
    load_existing_metadata,
    save_metadata_atomic,
    sync_metadata,
    DEFAULT_METADATA_OUTPUT_PATH,
)


def test_clean_text():
    assert clean_text("  hello   world  ") == "hello world"
    assert clean_text("TCMB   Döviz\n Kurları ") == "TCMB Döviz Kurları"
    assert clean_text("") is None
    assert clean_text(None) is None


def test_load_manifest_series():
    series = load_manifest_series()
    assert len(series) > 0, "Manifest must contain at least one series"
    assert all("code" in s and s["code"] for s in series)


def test_save_and_load_metadata_atomic(tmp_path):
    target = tmp_path / "test_meta.json"
    data = {"TP.TEST": {"SERIE_CODE": "TP.TEST", "SERIE_NAME": "Test Series"}}

    saved_path = save_metadata_atomic(data, target)
    assert saved_path.exists()

    loaded = load_existing_metadata(target)
    assert loaded == data


@pytest.mark.skipif(not DEFAULT_METADATA_OUTPUT_PATH.exists(), reason="metadata_raw.json does not exist yet")
def test_sync_metadata_idempotency_skip():
    """Verifies that calling sync_metadata when all series are present performs a clean skip."""
    meta = sync_metadata()
    assert isinstance(meta, dict)
    assert len(meta) >= len(load_manifest_series())
    assert "TP.DK.USD.A.YTL" in meta
    assert "TP.KTF10" in meta
