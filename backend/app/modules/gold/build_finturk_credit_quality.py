import pandas as pd
from pathlib import Path
import json

def build_gold_finturk(
    aligned_obs_path: Path,
    gold_dir: Path
) -> None:
    """
    Builds the gold_finturk_province_credit_quality table.
    Grain: province and quarter.
    """
    print("Reading aligned observations...")
    obs_df = pd.read_parquet(aligned_obs_path)
    
    # Ensure date is datetime
    if not pd.api.types.is_datetime64_any_dtype(obs_df['date']):
        obs_df['date'] = pd.to_datetime(obs_df['date'])
        
    # We only care about FinTurk source
    ft_df = obs_df[obs_df['source'] == 'BDDK_FINTURK'].copy()
    
    # Extract dimensions
    def extract_dim(dims_str, key):
        try:
            d = json.loads(dims_str)
            return d.get(key)
        except:
            return None
            
    ft_df['province'] = ft_df['dims'].apply(lambda x: extract_dim(x, 'province'))
    ft_df['geo_level'] = ft_df['dims'].apply(lambda x: extract_dim(x, 'geo_level'))
    ft_df['plate_code'] = ft_df['dims'].apply(lambda x: extract_dim(x, 'plate_code'))
    
    # Filter to only geo_level=province or Yurt Dışı (which might have geo_level=other or province="Yurt Dışı")
    # Actually, the requirement says "Only geo_level=province should enter province rankings; Yurt Dışı remains separately identifiable."
    # Let's keep geo_level in the output so consumers can filter.
    
    # Target series
    cash_loans_id = "BDDK_FINTURK:t1:nakdikrediler"
    npl_id = "BDDK_FINTURK:t1:takiptekialacaklar"
    # From phase 3: housing_loans (t1 doesn't have it directly, but maybe t1:konut_kredileri, or we skip if not present)
    # Actually, we will just pivot by series_id
    
    pivot_df = ft_df.pivot_table(
        index=['date', 'province', 'geo_level', 'plate_code'],
        columns='series_id',
        values='value',
        aggfunc='last'
    ).reset_index()
    
    # Rename columns if they exist
    rename_map = {
        cash_loans_id: 'total_cash_loans',
        npl_id: 'nonperforming_receivables',
        "BDDK_FINTURK:t1:konut_kredileri": 'housing_loans'  # Just in case
    }
    
    # Only rename columns that actually exist in the pivot
    existing_renames = {k: v for k, v in rename_map.items() if k in pivot_df.columns}
    pivot_df.rename(columns=existing_renames, inplace=True)
    
    # Ensure columns exist even if no data
    for col in rename_map.values():
        if col not in pivot_df.columns:
            pivot_df[col] = None
            
    # Calculate NPL ratio
    pivot_df['npl_ratio'] = pivot_df['nonperforming_receivables'] / (pivot_df['total_cash_loans'] + pivot_df['nonperforming_receivables'])
    
    # Select final columns
    final_cols = [
        'date', 'province', 'geo_level', 'plate_code',
        'total_cash_loans', 'nonperforming_receivables', 'npl_ratio', 'housing_loans'
    ]
    # In case there are other series, we drop them for this curated table
    final_df = pivot_df[final_cols].copy()
    
    # Sort
    final_df.sort_values(['date', 'plate_code', 'province'], inplace=True)
    
    out_path = gold_dir / "gold_finturk_province_credit_quality.parquet"
    print(f"Writing {len(final_df)} rows to {out_path}")
    gold_dir.mkdir(parents=True, exist_ok=True)
    final_df.to_parquet(out_path, index=False)
    print("Done.")

if __name__ == "__main__":
    project_root = Path(__file__).parent.parent.parent.parent.parent
    aligned_obs = project_root / "data" / "aligned" / "monthly" / "observations.parquet"
    gold_dir = project_root / "data" / "gold"
    
    build_gold_finturk(aligned_obs, gold_dir)
