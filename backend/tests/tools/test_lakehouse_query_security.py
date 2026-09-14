"""Tests for lakehouse_query security defenses (read-only enforcement & keyword validation)."""
from __future__ import annotations

import duckdb
import pytest

from backend.app.tools.lakehouse_query import (
    FORBIDDEN_KEYWORDS,
    LakehouseQueryTool,
    validate_query_safety,
)


def test_validate_query_safety_blocks_forbidden_keywords():
    for kw in FORBIDDEN_KEYWORDS:
        is_safe, error = validate_query_safety(f"SELECT * FROM test; {kw} TABLE abc;")
        assert is_safe is False
        assert f"Bu sorgu türü ({kw}) desteklenmiyor" in error


def test_validate_query_safety_allows_safe_select():
    is_safe, error = validate_query_safety("SELECT date, value FROM gold_housing_credit_market WHERE value > 10")
    assert is_safe is True
    assert error is None


def test_lakehouse_query_blocks_malicious_column_or_table_names():
    tool = LakehouseQueryTool()

    # Tablo adı manipülasyonu
    res_table = tool.run(
        tool.Input(
            table="gold_housing_credit_market; DROP TABLE gold_periodic_change; --",
            columns=["date"],
        )
    )
    assert res_table.success is False
    assert "Tablo bulunamadi" in res_table.error

    # Kolon adı SQL injection denemesi
    res_col = tool.run(
        tool.Input(
            table="gold_housing_credit_market",
            columns=["date", "'; DROP TABLE gold_periodic_change; --"],
        )
    )
    assert res_col.success is False
    assert "Kolon bulunamadi" in res_col.error


def test_lakehouse_db_connection_is_read_only(tmp_path):
    # Gerçek duckdb dosyasında read_only=True ile yazma denendiğinde PermissionError veya CatalogException fırlatıldığını doğrula
    db_file = tmp_path / "test_ro.duckdb"
    con_init = duckdb.connect(str(db_file))
    con_init.execute("CREATE TABLE t1 (id INT)")
    con_init.close()

    con_ro = duckdb.connect(str(db_file), read_only=True)
    with pytest.raises(duckdb.Error):
        con_ro.execute("INSERT INTO t1 VALUES (1)")
    with pytest.raises(duckdb.Error):
        con_ro.execute("DROP TABLE t1")
    con_ro.close()
