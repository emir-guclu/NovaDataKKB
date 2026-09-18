"""Tests for the inline observations parser (lakehouse dışı veri girdisi)."""
from __future__ import annotations

import pytest

from backend.app.prompts.loader import get_system_prompt
from backend.app.services.inline_series import parse_inline_observations


def _rows(values, start_month=1):
    return [{"date": f"2024-{start_month + i:02d}-01", "value": v} for i, v in enumerate(values)]


def test_turkish_number_format_is_parsed():
    data, warnings = parse_inline_observations(
        [
            {"date": "2024-01-01", "value": "1.234,56"},
            {"date": "2024-02-01", "value": "%12,5"},
            {"date": "2024-03-01", "value": "1.234.567"},
            {"date": "2024-04-01", "value": " 42 "},
        ]
    )
    assert [v for _, v in data] == [1234.56, 12.5, 1234567.0, 42.0]
    assert warnings == []


def test_four_date_formats_are_recognised():
    data, warnings = parse_inline_observations(
        [
            {"date": "2024-01-15", "value": 1},
            {"date": "2024-02", "value": 2},
            {"date": "15.03.2024", "value": 3},
            {"date": "15/04/2024", "value": 4},
        ]
    )
    assert [d for d, _ in data] == ["2024-01-15", "2024-02-29", "2024-03-15", "2024-04-15"]
    assert warnings == []


def test_alternative_key_names_are_accepted():
    data, _ = parse_inline_observations(
        [
            {"Tarih": "2024-01-01", "kapanis": 10},
            {"TARİH".replace("İ", "i"): "2024-02-01", "değer": 11},
            {"DATE": "2024-03-01", "VALUE": 12},
        ]
    )
    assert [v for _, v in data] == [10.0, 11.0, 12.0]


def test_malformed_rows_are_skipped_with_warning():
    rows = _rows([1, 2, 3, 4]) + [{"date": "bozuk", "value": 5}, {"date": "2024-06-01", "value": "abc"}, "x"]
    data, warnings = parse_inline_observations(rows)
    assert len(data) == 4
    assert len(warnings) == 3
    assert any("Satır 5" in w and "tarih" in w for w in warnings)
    assert any("Satır 6" in w and "değer" in w for w in warnings)


def test_duplicate_dates_keep_last_and_warn():
    data, warnings = parse_inline_observations(
        [
            {"date": "2024-01-01", "value": 1},
            {"date": "2024-01-01", "value": 9},
            {"date": "2024-02-01", "value": 2},
            {"date": "2024-03-01", "value": 3},
        ]
    )
    assert data[0] == ("2024-01-01", 9.0)
    assert any("tekrarlanan" in w for w in warnings)


def test_unsorted_input_is_sorted_by_date():
    data, _ = parse_inline_observations(
        [
            {"date": "2024-03-01", "value": 3},
            {"date": "2024-01-01", "value": 1},
            {"date": "2024-02-01", "value": 2},
        ]
    )
    assert [d for d, _ in data] == ["2024-01-01", "2024-02-01", "2024-03-01"]


def test_below_fifty_percent_parse_ratio_raises():
    rows = _rows([1, 2]) + [{"date": "x", "value": 1}] * 3
    with pytest.raises(ValueError, match=r"yalnızca %40'i ayrıştırılabildi"):
        parse_inline_observations(rows)


def test_fewer_than_three_valid_observations_raises():
    with pytest.raises(ValueError, match="en az 3"):
        parse_inline_observations(_rows([1, 2]))
    with pytest.raises(ValueError, match="en az 3"):
        parse_inline_observations([])


def test_date_range_filter_and_too_narrow_range():
    rows = _rows([1, 2, 3, 4, 5])
    data, _ = parse_inline_observations(rows, start_date="2024-02-01", end_date="2024-04-01")
    assert [v for _, v in data] == [2.0, 3.0, 4.0]
    with pytest.raises(ValueError, match="tarih aralığında"):
        parse_inline_observations(rows, start_date="2024-02-01", end_date="2024-03-01")


def test_mom_pct_change_is_computed_and_first_observation_dropped():
    data, warnings = parse_inline_observations(_rows([100, 110, 99]), metric="mom_pct_change")
    assert [d for d, _ in data] == ["2024-02-01", "2024-03-01"]
    assert data[0][1] == pytest.approx(10.0)
    assert data[1][1] == pytest.approx(-10.0)
    assert any("ardışık gözlemler" in w for w in warnings)


@pytest.mark.parametrize("metric", ["yoy_pct_change", "mom_abs_change", "yoy_abs_change", "foo"])
def test_unsupported_metric_raises(metric):
    with pytest.raises(ValueError, match="yalnızca 'value' ve 'mom_pct_change'"):
        parse_inline_observations(_rows([1, 2, 3]), metric=metric)


def test_system_prompt_documents_inline_observations_and_still_renders():
    prompt = get_system_prompt(today="2026-09-19")
    assert "LAKEHOUSE DIŞI VERİYİ ANALİZ ETME" in prompt
    assert '[{"date": "YYYY-MM-DD", "value": 123.4}, ...]' in prompt
    assert prompt.index("LAKEHOUSE DIŞI VERİYİ") < prompt.index("İLERİ DÜZEY ANALİTİK ARAÇLAR")
