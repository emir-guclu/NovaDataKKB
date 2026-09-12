import pandas as pd
from pathlib import Path
from app.modules.gold.review_guard import require_reviewed_series

def build_gold_precious_metals(
    evds_silver_obs_path: Path,
    gold_dir: Path
) -> None:
    """
    Builds the precious metals ratio tables (daily and monthly).
    Strictly follows the daily-ratio-first rule:
    ratio = daily_gold / daily_silver, NOT monthly_avg_gold / monthly_avg_silver.
    """
    print("Reading EVDS silver observations...")
    obs_df = pd.read_parquet(evds_silver_obs_path)
    meta_df = pd.read_parquet(evds_silver_obs_path.parent / "series_metadata.parquet")
    require_reviewed_series(
        meta_df,
        ["EVDS:TP.ALTINPIYASA.KAP03", "EVDS:TP.GUMUSPIYASA.KAP03"],
        "gold_precious_metal_ratios",
    )
    
    # Ensure date is datetime
    if not pd.api.types.is_datetime64_any_dtype(obs_df['date']):
        obs_df['date'] = pd.to_datetime(obs_df['date'])
        
    # Extract Gold
    gold_df = obs_df[obs_df['series_id'] == 'EVDS:TP.ALTINPIYASA.KAP03'][['date', 'value']].rename(columns={'value': 'gold_usd_ons_close'})
    
    # Extract Silver
    silver_df = obs_df[obs_df['series_id'] == 'EVDS:TP.GUMUSPIYASA.KAP03'][['date', 'value']].rename(columns={'value': 'silver_usd_ons_close'})
    
    # Join on date (inner join to get common trading days)
    daily_df = gold_df.merge(silver_df, on='date', how='inner')
    
    # Calculate daily ratio
    daily_df['gold_silver_ratio'] = daily_df['gold_usd_ons_close'] / daily_df['silver_usd_ons_close']
    
    # Sort
    daily_df.sort_values('date', inplace=True)
    daily_df.reset_index(drop=True, inplace=True)
    
    # Write Daily
    gold_dir.mkdir(parents=True, exist_ok=True)
    daily_path = gold_dir / "gold_precious_metal_ratios_daily.parquet"
    print(f"Writing {len(daily_df)} rows to {daily_path}")
    daily_df.to_parquet(daily_path, index=False)
    
    # Build Monthly companion
    # Set index to date, resample to Month End
    monthly_df = daily_df.set_index('date').resample('ME').mean()
    monthly_df.reset_index(inplace=True)
    
    # Calculate MoM pct change
    monthly_df['gold_mom_pct_change'] = monthly_df['gold_usd_ons_close'].pct_change()
    monthly_df['silver_mom_pct_change'] = monthly_df['silver_usd_ons_close'].pct_change()
    monthly_df['ratio_mom_pct_change'] = monthly_df['gold_silver_ratio'].pct_change()
    
    monthly_path = gold_dir / "gold_precious_metal_ratios_monthly.parquet"
    print(f"Writing {len(monthly_df)} rows to {monthly_path}")
    monthly_df.to_parquet(monthly_path, index=False)
    print("Done.")

if __name__ == "__main__":
    project_root = Path(__file__).parent.parent.parent.parent.parent
    evds_silver_obs = project_root / "data" / "silver" / "evds" / "observations.parquet"
    gold_dir = project_root / "data" / "gold"
    
    build_gold_precious_metals(evds_silver_obs, gold_dir)
