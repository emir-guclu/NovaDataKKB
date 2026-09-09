"""Utilities for converting cumulative BDDK series into periodic values."""

from typing import Literal

import pandas as pd


AccumulationType = Literal["none", "ytd", "since_start"]


def decumulate(
    series: pd.Series,
    accumulation: AccumulationType,
) -> pd.Series:
    """
    Convert a cumulative series into periodic values.

    Parameters
    ----------
    series:
        A pandas Series whose index must be datetime-like.

    accumulation:
        - "none": return values unchanged.
        - "ytd": calculate differences within each calendar year.
          The first observation of each year keeps its original value.
        - "since_start": calculate a global difference.
          The first observation keeps its original value.

    Returns
    -------
    pd.Series
        Periodic values aligned to the original index.

    Notes
    -----
    This function does NOT infer whether a series is cumulative.
    That classification must come from manually reviewed series metadata.
    """
    if accumulation not in {"none", "ytd", "since_start"}:
        raise ValueError(
            "accumulation must be one of: 'none', 'ytd', 'since_start'"
        )

    if accumulation == "none":
        return series.copy()

    if not isinstance(series.index, pd.DatetimeIndex):
        raise TypeError(
            "series index must be a pandas.DatetimeIndex for decumulation"
        )

    values = pd.to_numeric(series, errors="coerce")

    if accumulation == "since_start":
        result = values.diff()

        if not values.empty:
            result.iloc[0] = values.iloc[0]

        return result

    # YTD: difference only within the same calendar year.
    result = values.groupby(values.index.year).diff()

    # First observation of each year must retain its cumulative raw value.
    first_of_year = ~values.index.year.duplicated()
    result.loc[first_of_year] = values.loc[first_of_year]

    return result
