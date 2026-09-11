import pandas as pd
from pathlib import Path
import json

def build_gold_periodic_change(
    aligned_obs_path: Path,
    aligned_meta_path: Path,
    output_path: Path
) -> None:
    """
    Builds the gold_periodic_change table.
    Computes MoM and YoY absolute and percentage changes for all series.
    """
    print("Reading aligned observations and metadata...")
    obs_df = pd.read_parquet(aligned_obs_path)
    meta_df = pd.read_parquet(aligned_meta_path)
    
    # Ensure date is datetime
    obs_df['date'] = pd.to_datetime(obs_df['date'])
    
    # Extract only necessary columns from observations
    df = obs_df[['date', 'series_id', 'value', 'source', 'unit', 'dims']].copy()
    
    # Extract nature from metadata and merge
    meta_subset = meta_df[['series_id', 'nature']].drop_duplicates()
    df = df.merge(meta_subset, on='series_id', how='left')
    
    # Sort to ensure proper shifting
    df.sort_values(by=['series_id', 'dims', 'date'], inplace=True)
    df.reset_index(drop=True, inplace=True)
    
    # Group by series_id and dims for shifting
    group = df.groupby(['series_id', 'dims'])
    
    # 1-month shift
    df['prev_date_1'] = group['date'].shift(1)
    df['prev_value_1'] = group['value'].shift(1)
    
    # 12-month shift
    df['prev_date_12'] = group['date'].shift(12)
    df['prev_value_12'] = group['value'].shift(12)
    
    # Check validity of shifts (1 month and 12 months respectively)
    def months_diff(d1, d2):
        return (d1.dt.year - d2.dt.year) * 12 + (d1.dt.month - d2.dt.month)
    
    valid_mom = months_diff(df['date'], df['prev_date_1']) == 1
    valid_yoy = months_diff(df['date'], df['prev_date_12']) == 12
    
    # Compute MoM changes
    df['mom_abs_change'] = None
    df['mom_pct_change'] = None
    df.loc[valid_mom, 'mom_abs_change'] = df['value'] - df['prev_value_1']
    df.loc[valid_mom, 'mom_pct_change'] = (df['value'] - df['prev_value_1']) / df['prev_value_1'].abs()
    
    # Compute YoY changes
    df['yoy_abs_change'] = None
    df['yoy_pct_change'] = None
    df.loc[valid_yoy, 'yoy_abs_change'] = df['value'] - df['prev_value_12']
    df.loc[valid_yoy, 'yoy_pct_change'] = (df['value'] - df['prev_value_12']) / df['prev_value_12'].abs()
    
    # Select output columns
    output_cols = [
        'date',
        'series_id',
        'value',
        'mom_abs_change',
        'mom_pct_change',
        'yoy_abs_change',
        'yoy_pct_change',
        'source',
        'nature',
        'unit',
        'dims'
    ]
    
    final_df = df[output_cols].copy()
    
    print(f"Writing {len(final_df)} rows to {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    final_df.to_parquet(output_path, index=False)
    print("Done.")

if __name__ == "__main__":
    project_root = Path(__file__).parent.parent.parent.parent.parent
    aligned_obs = project_root / "data" / "aligned" / "monthly" / "observations.parquet"
    aligned_meta = project_root / "data" / "aligned" / "monthly" / "series_metadata.parquet"
    gold_out = project_root / "data" / "gold" / "gold_periodic_change.parquet"
    
    build_gold_periodic_change(aligned_obs, aligned_meta, gold_out)
