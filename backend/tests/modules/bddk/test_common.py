import pytest

from app.modules.bddk.common import (
    slugify as bronze_slugify,
)
from app.modules.bddk.parsers.common import (
    extract_unit_hint,
    parse_tr_number,
)


def test_slugify_turkish_text():
    assert (
        bronze_slugify(
            "Seçilmiş Sektörel Krediler (Bin TL)"
        )
        == "secilmis_sektorel_krediler_bin_tl"
    )


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1.234.567,89", 1234567.89),
        ("334.521,04", 334521.04),
        ("16.955.526,22", 16955526.22),
        ("12,5%", 12.5),
        ("%12,50", 12.5),
        ("-1.234,50", -1234.50),
        ("1000", 1000.0),
        (123.45, 123.45),
        ("-", None),
        ("", None),
        ("—", None),
        ("n.a.", None),
        ("veri yok", None),
        (None, None),
    ],
)
def test_parse_tr_number(raw, expected):
    result = parse_tr_number(raw)

    if expected is None:
        assert result is None
    else:
        assert result == pytest.approx(expected)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Bilanço (milyon TL), Dönem:2021/1", "milyon TL"),
        (
            "Altın Kredileri ve Altın Mevduatı (Bin TL)",
            "bin TL",
        ),
        ("Oranlar (%)", "%"),
        ("Şubeler (Adet)", "adet"),
        ("Krediler (TL)", "TL"),
        ("Başlıkta birim yok", None),
        (None, None),
    ],
)
def test_extract_unit_hint(raw, expected):
    assert extract_unit_hint(raw) == expected
