"""Tests for lakehouse_query security defenses (read-only enforcement & keyword validation)."""
from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from backend.app.tools.lakehouse_query import (
    FORBIDDEN_KEYWORDS,
    LakehouseQueryTool,
    _connect_lakehouse,
    validate_query_safety,
)

_LAKEHOUSE_DB = Path(__file__).resolve().parents[3] / "data" / "lakehouse.duckdb"
_requires_lakehouse = pytest.mark.skipif(
    not _LAKEHOUSE_DB.exists(),
    reason="Lakehouse verisi yok (data/lakehouse.duckdb). SETUP.md'deki pipeline ile üretilir.",
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


def test_validate_query_safety_allows_columns_containing_keywords():
    """created_at / updated_at gibi kolon adları yanlışlıkla engellenmemeli."""
    for sql in [
        'SELECT "created_at" FROM t',
        'SELECT "updated_at", value FROM t',
        'SELECT "copy_count" FROM t',
        'SELECT "insert_date" FROM t',
    ]:
        is_safe, error = validate_query_safety(sql)
        assert is_safe is True, f"Yanlış pozitif: {sql} -> {error}"
        assert error is None


# --- Kökteki tests/tools/test_lakehouse_query_security.py dosyasından birleştirilen testler ---
@_requires_lakehouse
def test_connect_lakehouse_is_readonly():
    con = _connect_lakehouse()
    try:
        with pytest.raises(duckdb.Error):
            con.execute("CREATE TABLE security_test_tbl (id INT)")
    finally:
        con.close()


@_requires_lakehouse
def test_lakehouse_query_tool_blocks_injection_attempt():
    tool = LakehouseQueryTool()
    # Tablo adı veya kolon alanında injection denemesi
    malicious_input = LakehouseQueryTool.Input(
        table="gold_housing_credit_market'; DROP TABLE gold_housing_credit_market; --",
        columns=["date"],
    )
    result = tool.run(malicious_input)
    assert result.success is False
    assert "bulunamadi" in result.error.lower() or "desteklenmiyor" in result.error.lower()


@_requires_lakehouse
def test_lakehouse_query_tool_legitimate_query():
    tool = LakehouseQueryTool()
    # Mevcut bir gold view/table sorgusu
    valid_input = LakehouseQueryTool.Input(
        table="gold_housing_credit_market",
        columns=["date"],
        limit=2,
    )
    result = tool.run(valid_input)
    if result.success:
        assert len(result.rows) <= 2
        assert result.table == "gold_housing_credit_market"
    else:
        # Eğer test ortamında lakehouse db henüz oluşturulmamışsa 'bulunamadi' dönebilir ama SQL/syntax hatası olmamalı
        assert "Lakehouse bulunamadi" in result.error
