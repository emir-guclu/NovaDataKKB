"""Tests for the numeric grounding check (Doğruluk Kontrolü)."""
from __future__ import annotations

from backend.app.services.grounding import _candidates, check_grounding


def test_turkish_formatted_number_matches_float_in_tool_output_within_tolerance():
    result = check_grounding("Oran %42,1 olarak gerçekleşti.", ['{"value": 42.13}'])
    assert result["checked"] == 1
    assert result["grounded"] == 1
    assert result["ungrounded"] == []
    assert result["ratio"] == 1.0


def test_ambiguous_single_dot_is_tried_as_thousands_and_decimal():
    assert sorted(_candidates("1.234")) == [1.234, 1234.0]
    assert _candidates("1,234") == [1.234, 1234.0]
    assert _candidates("42,1") == [42.1]
    assert _candidates("1.234,56") == [1234.56]
    assert _candidates("1,234.56") == [1234.56]
    assert _candidates("abc") == []

    # Cevap Türkçe (1.234 = 1234), tool çıktısı tam sayı olarak 1234 içeriyor
    assert check_grounding("Hacim 1.234 milyon TL.", ['{"value": 1234}'])["grounded"] == 1
    # Cevap "1.234" ama tool çıktısında ondalık 1.234 var
    assert check_grounding("Katsayı 1.234 bulundu.", ['{"coef": 1.234}'])["grounded"] == 1


def test_fabricated_number_is_caught():
    result = check_grounding(
        "Hacim 999.999 milyon TL, artış %12,5.",
        ['{"value": 12.5, "other": 3.3}'],
    )
    assert result["checked"] == 2
    assert result["grounded"] == 1
    assert result["ungrounded"] == ["999.999"]
    assert result["ratio"] == 0.5


def test_years_are_skipped():
    result = check_grounding("2021 ile 2024 arasında değişim.", ['{"value": 5.5}'])
    assert result["checked"] == 0
    assert result["ratio"] == 1.0


def test_dates_are_not_counted_as_numbers():
    result = check_grounding("En yüksek değer 2023-03-31 tarihinde, 31.03.2023 idi.", ['{"x": 1}'])
    assert result["checked"] == 0


def test_small_integers_are_skipped_such_as_list_numbers():
    answer = "1. Birinci madde\n2. İkinci madde\n3. Üçüncü madde\nToplam 12 ay."
    result = check_grounding(answer, ['{"value": 999}'])
    assert result == {"checked": 0, "grounded": 0, "ungrounded": [], "ratio": 1.0, "sources": {"tool": 0, "document": 0}}


def test_markdown_table_alignment_rows_are_ignored():
    answer = "| Ay | Değer |\n|---|:---:|\n| Mart | 45,5 |"
    result = check_grounding(answer, ['{"v": 45.5}'])
    assert result["checked"] == 1
    assert result["grounded"] == 1


def test_identifiers_with_digits_are_not_numbers():
    result = check_grounding("Model Qwen3-27B, seri TP.AB.B1 ve KTR100.", ['{"v": 1}'])
    assert result["checked"] == 0


def test_sign_and_range_handling():
    assert check_grounding("Değişim -2,5 puan.", ['{"d": 2.5}'])["grounded"] == 1
    assert check_grounding("Aralık 50-70 arası.", ['{"a": 50, "b": 70}'])["grounded"] == 2


def test_empty_tool_outputs_with_numbers_are_ungrounded_but_nothing_to_check_without_numbers():
    assert check_grounding("Sayı içermeyen cevap.", []) == {
        "checked": 0, "grounded": 0, "ungrounded": [], "ratio": 1.0, "sources": {"tool": 0, "document": 0},
    }
    result = check_grounding("Değer 345,6.", [])
    assert result["checked"] == 1
    assert result["grounded"] == 0
    assert result["ungrounded"] == ["345,6"]


def test_empty_tool_outputs_and_empty_answer_gives_checked_zero():
    result = check_grounding("", [])
    assert result["checked"] == 0
    assert result["ratio"] == 1.0


def test_malformed_input_never_raises():
    expected = {"checked": 0, "grounded": 0, "ungrounded": [], "ratio": 1.0, "sources": {"tool": 0, "document": 0}}
    assert check_grounding(None, None) == expected  # type: ignore[arg-type]
    assert check_grounding(123, ["x"]) == expected  # type: ignore[arg-type]
    assert check_grounding("42,5", "yanlış tip") == expected  # type: ignore[arg-type]
    result = check_grounding("42,5", [None, 5, b"x", '{"v": 42.5}'])  # type: ignore[list-item]
    assert result["grounded"] == 1


DOCUMENT = "| Ay | Değer |\n|---|---|\n| Mart | 1.234,5 |\n| Nisan | 67,8 |"


def test_extra_sources_ground_numbers_missing_from_tool_outputs():
    result = check_grounding("Mart değeri 1.234,5, Nisan 67,8.", [], [DOCUMENT])
    assert result["checked"] == 2
    assert result["grounded"] == 2
    assert result["ungrounded"] == []
    assert result["sources"] == {"tool": 0, "document": 2}


def test_source_split_counts_number_in_both_as_tool():
    answer = "Mart 1.234,5 ve Nisan 67,8; ayrıca uydurma 555,5."
    result = check_grounding(answer, ['{"v": 1234.5}'], [DOCUMENT])
    assert result["checked"] == 3
    assert result["grounded"] == 2
    assert result["ungrounded"] == ["555,5"]
    assert result["sources"] == {"tool": 1, "document": 1}


def test_two_argument_call_still_works_and_reports_all_from_tool():
    result = check_grounding("Değer 42,1.", ['{"value": 42.13}'])
    assert result["grounded"] == 1
    assert result["sources"] == {"tool": 1, "document": 0}
    assert check_grounding("Değer 42,1.", ['{"value": 42.13}'], None) == result


def test_malformed_extra_sources_do_not_raise():
    result = check_grounding("Değer 345,6.", [], "yanlış tip")  # type: ignore[arg-type]
    assert result["ungrounded"] == ["345,6"]
    result = check_grounding("Değer 345,6.", [], [None, 7, "değer 345,6"])  # type: ignore[list-item]
    assert result["sources"] == {"tool": 0, "document": 1}
