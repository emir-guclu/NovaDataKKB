import pytest
from pathlib import Path

LAKEHOUSE_DATA = [
    Path(__file__).resolve().parents[3] / "data" / "lakehouse.duckdb",
    Path(__file__).resolve().parents[3] / "data" / "gold" / "gold_housing_credit_market.parquet",
]
pytestmark = pytest.mark.skipif(
    not all(p.exists() for p in LAKEHOUSE_DATA),
    reason="Lakehouse verisi yok (data/lakehouse.duckdb, data/gold). SETUP.md'deki pipeline ile üretilir."
)

from pydantic import ValidationError

from backend.app.tools.lakehouse_query import LakehouseQueryTool


def test_lakehouse_query_success_with_real_gold_data():
    tool = LakehouseQueryTool()
    result = tool.run(
        tool.Input(
            table="gold_housing_credit_market",
            columns=["date", "konut_kredisi_hacmi_tp", "konut_kredisi_faiz_orani"],
            order_by="date",
            order_direction="desc",
            limit=1,
        )
    )

    assert result.success is True
    assert result.error is None
    assert result.table == "gold_housing_credit_market"
    assert result.row_count == 1
    assert result.rows[0]["date"].startswith("2026-06-30")
    assert result.rows[0]["konut_kredisi_hacmi_tp"] == pytest.approx(801375.536)
    assert result.rows[0]["konut_kredisi_faiz_orani"] == pytest.approx(39.33)


def test_lakehouse_query_missing_table_returns_structured_error():
    tool = LakehouseQueryTool()
    result = tool.run(
        tool.Input(
            table="missing_table",
            columns=["date"],
        )
    )

    assert result.success is False
    assert result.error is not None
    assert "Tablo bulunamadi" in result.error


def test_lakehouse_query_rejects_unsafe_column():
    tool = LakehouseQueryTool()
    result = tool.run(
        tool.Input(
            table="gold_housing_credit_market",
            columns=["date; DROP TABLE gold_housing_credit_market"],
        )
    )

    assert result.success is False
    assert result.error is not None
    assert "Kolon bulunamadi" in result.error


def test_lakehouse_query_validation_error():
    tool = LakehouseQueryTool()

    with pytest.raises(ValidationError):
        tool.Input(table="gold_housing_credit_market")


def test_lakehouse_query_finturk_preserves_column_units():
    tool = LakehouseQueryTool()
    result = tool.run(
        tool.Input(
            table="gold_finturk_province_credit_quality",
            columns=[
                "date",
                "province",
                "total_cash_loans",
                "nonperforming_receivables",
                "npl_ratio",
            ],
            filters={"province": "İstanbul"},
            order_by="date",
            order_direction="desc",
            limit=1,
        )
    )

    assert result.success is True
    assert result.row_count == 1
    assert result.column_units["total_cash_loans"] == "bin TL"
    assert result.column_units["nonperforming_receivables"] == "bin TL"
    assert result.column_units["npl_ratio"] == "ratio"
    assert result.rows[0]["total_cash_loans"] == pytest.approx(9037199663.0)
