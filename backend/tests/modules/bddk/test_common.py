from app.modules.bddk.common import (
    parse_tr_number,
    slugify,
)


def test_slugify_turkish_text():
    assert (
        slugify("Seçilmiş Sektörel Krediler (Bin TL)")
        == "secilmis_sektorel_krediler_bin_tl"
    )


def test_parse_tr_number_large_value():
    assert parse_tr_number(
        "16.955.526,22"
    ) == 16955526.22


def test_parse_tr_number_percentage():
    assert parse_tr_number(
        "%12,50"
    ) == 12.5


def test_parse_tr_number_empty_values():
    assert parse_tr_number(None) is None
    assert parse_tr_number("") is None
    assert parse_tr_number("-") is None
    assert parse_tr_number("—") is None


def test_parse_tr_number_invalid_text():
    assert parse_tr_number("veri yok") is None
