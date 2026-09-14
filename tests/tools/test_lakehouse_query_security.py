import pytest
import duckdb

from backend.app.tools.lakehouse_query import (
    LakehouseQueryTool,
    _connect_lakehouse,
    validate_query_safety,
    FORBIDDEN_KEYWORDS,
)


def test_validate_query_safety_detects_forbidden_keywords():
    for kw in FORBIDDEN_KEYWORDS:
        is_safe, err = validate_query_safety(f"SELECT * FROM tbl; {kw} TABLE test")
        assert not is_safe
        assert kw in err

    is_safe, err = validate_query_safety("SELECT col1, col2 FROM my_table WHERE date = '2024-01-01'")
    assert is_safe
    assert err is None


def test_connect_lakehouse_is_readonly():
    con = _connect_lakehouse()
    try:
        with pytest.raises(duckdb.Error):
            con.execute("CREATE TABLE security_test_tbl (id INT)")
    finally:
        con.close()


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
