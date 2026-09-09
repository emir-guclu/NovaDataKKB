import pandas as pd
import pytest

from app.modules.bddk.parsers.decumulate import decumulate


def test_decumulate_none_returns_same_values():
    idx = pd.to_datetime(["2021-01-01", "2021-02-01", "2021-03-01"])
    s = pd.Series([16313.305, 16268.733, 17161.216], index=idx)

    result = decumulate(s, "none")

    assert result.tolist() == pytest.approx([
        16313.305,
        16268.733,
        17161.216,
    ])


def test_decumulate_ytd_real_bddk_interest_income():
    """
    Real BDDK Monthly values:
    Kar Zarar -> Kredilerden Alınan Faizler (Kar Payları) -> TP
    """
    idx = pd.to_datetime([
        "2021-01-01",
        "2021-02-01",
        "2021-03-01",
    ])

    cumulative = pd.Series([
        25382.899,
        49154.549,
        77130.808,
    ], index=idx)

    result = decumulate(cumulative, "ytd")

    assert result.iloc[0] == pytest.approx(25382.899)
    assert result.iloc[1] == pytest.approx(23771.650)
    assert result.iloc[2] == pytest.approx(27976.259)


def test_decumulate_ytd_resets_at_new_year():
    """
    The January observation of a new year must keep its own value
    instead of being differenced against the previous December.
    """
    idx = pd.to_datetime([
        "2021-11-01",
        "2021-12-01",
        "2022-01-01",
        "2022-02-01",
    ])

    cumulative = pd.Series([
        327647.677,
        365098.455,
        39274.998,
        76416.459,
    ], index=idx)

    result = decumulate(cumulative, "ytd")

    assert result.iloc[0] == pytest.approx(327647.677)
    assert result.iloc[1] == pytest.approx(37450.778)

    # Critical year-reset behavior
    assert result.iloc[2] == pytest.approx(39274.998)

    assert result.iloc[3] == pytest.approx(37141.461)


def test_decumulate_since_start():
    idx = pd.to_datetime([
        "2021-01-01",
        "2021-02-01",
        "2021-03-01",
    ])

    cumulative = pd.Series([
        100.0,
        135.0,
        160.0,
    ], index=idx)

    result = decumulate(cumulative, "since_start")

    assert result.tolist() == pytest.approx([
        100.0,
        35.0,
        25.0,
    ])


def test_decumulate_rejects_invalid_accumulation():
    idx = pd.to_datetime(["2021-01-01"])
    s = pd.Series([1.0], index=idx)

    with pytest.raises(ValueError):
        decumulate(s, "invalid")


def test_decumulate_requires_datetime_index_for_ytd():
    s = pd.Series([100.0, 120.0])

    with pytest.raises(TypeError):
        decumulate(s, "ytd")
