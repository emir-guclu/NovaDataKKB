from backend.app.models.lakehouse_models import lakehouse_metadata


def test_finturk_gold_unit_contract():
    table = lakehouse_metadata.tables["gold_finturk_province_credit_quality"]

    assert table.c["total_cash_loans"].info["unit"] == "bin TL"
    assert table.c["nonperforming_receivables"].info["unit"] == "bin TL"
    assert table.c["housing_loans"].info["unit"] == "bin TL"
    assert table.c["npl_ratio"].info["unit"] == "ratio"

    assert "Bin TL" in table.c["total_cash_loans"].comment
    assert "Bin TL" in table.c["nonperforming_receivables"].comment
    assert "Bin TL" in table.c["housing_loans"].comment
