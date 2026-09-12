import pandas as pd


def reviewed_series_ids(meta_df: pd.DataFrame) -> set[str]:
    required = {"series_id", "nature_reviewed"}
    missing = required - set(meta_df.columns)
    if missing:
        raise ValueError(f"Gold review guard: metadata missing columns: {sorted(missing)}")
    return set(meta_df.loc[meta_df["nature_reviewed"].eq(True), "series_id"].dropna().astype(str))


def require_reviewed_series(meta_df: pd.DataFrame, series_ids: list[str], context: str) -> None:
    reviewed = reviewed_series_ids(meta_df)
    blocked = sorted(set(series_ids) - reviewed)
    if blocked:
        raise ValueError(f"Gold review guard ({context}): required series are missing or nature_reviewed is not True: {blocked}")
