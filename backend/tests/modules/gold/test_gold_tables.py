import pytest
import pandas as pd
from pathlib import Path
import numpy as np

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.parent
GOLD_DIR = PROJECT_ROOT / "data" / "gold"

def test_gold_periodic_change_calculation():
    """Verify mom_change_pct is correctly calculated in gold_periodic_change."""
    parquet_path = GOLD_DIR / "gold_periodic_change.parquet"
    assert parquet_path.exists()
    
    df = pd.read_parquet(parquet_path)
    
    # Pick a Monthly series to test MoM
    sample_series = "BDDK_MONTHLY:tuketici_kredileri:tuketici_kredileri_konut"
    sample_dims = '{"variable": "TP"}'
    sub_df = df[(df['series_id'] == sample_series) & (df['dims'] == sample_dims)].sort_values('date').copy()
    
    # Recalculate manually
    sub_df['manual_prev'] = sub_df['value'].shift(1)
    
    # We only verify where there are no gaps
    # Calculate months difference to ensure 1 month gap
    sub_df['diff_months'] = (sub_df['date'].dt.year - sub_df['date'].shift(1).dt.year) * 12 + (sub_df['date'].dt.month - sub_df['date'].shift(1).dt.month)
    valid_mom = sub_df['diff_months'] == 1
    
    sub_df.loc[valid_mom, 'manual_mom_abs'] = sub_df['value'] - sub_df['manual_prev']
    sub_df.loc[valid_mom, 'manual_mom_pct'] = (sub_df['value'] - sub_df['manual_prev']) / sub_df['manual_prev'].abs()
    
    # Assert
    # Use np.isclose to avoid floating point issues, dropping NAs
    merged = sub_df.dropna(subset=['mom_pct_change', 'manual_mom_pct'])
    assert len(merged) > 0, "No valid MoM calculations found"
    
    np.testing.assert_allclose(merged['mom_pct_change'].values, merged['manual_mom_pct'].values, rtol=1e-5)

def test_gold_housing_credit_market_types():
    """Verify column types and row counts for housing credit market."""
    parquet_path = GOLD_DIR / "gold_housing_credit_market.parquet"
    assert parquet_path.exists()
    
    df = pd.read_parquet(parquet_path)
    
    # Assert expected columns exist
    expected_cols = [
        'date', 
        'konut_kredisi_hacmi_tp', 
        'konut_kredisi_faiz_orani', 
        'konut_fiyat_endeksi', 
        'toplam_konut_satisi'
    ]
    for col in expected_cols:
        assert col in df.columns
        
    # Date should be datetime
    assert pd.api.types.is_datetime64_any_dtype(df['date'])
    
    # Other columns should be numeric
    assert pd.api.types.is_numeric_dtype(df['konut_kredisi_hacmi_tp'])
    
def test_gold_finturk_row_count():
    """Verify FinTurk province data is at the province/quarter grain."""
    parquet_path = GOLD_DIR / "gold_finturk_province_credit_quality.parquet"
    assert parquet_path.exists()
    
    df = pd.read_parquet(parquet_path)
    
    # The grain is date + province. We shouldn't have duplicate provinces on the same date.
    duplicates = df.duplicated(subset=['date', 'province'])
    assert not duplicates.any(), "Duplicate province records found for a single date."
