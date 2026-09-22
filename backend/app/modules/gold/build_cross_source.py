import pandas as pd
from pathlib import Path
import json
from dataclasses import dataclass
from typing import Optional, Dict
import sys

_project_root = Path(__file__).parent.parent.parent.parent.parent
_backend_path = str(_project_root / "backend")
if _backend_path not in sys.path:
    sys.path.insert(0, _backend_path)

try:
    from app.modules.gold.review_guard import reviewed_series_ids
except ModuleNotFoundError:
    from backend.app.modules.gold.review_guard import reviewed_series_ids

@dataclass
class ColumnDef:
    series_id: str
    dim_key: Optional[str] = None
    dim_value: Optional[str] = None

def build_cross_source_gold_table(
    table_name: str,
    obs_df: pd.DataFrame,
    columns_config: Dict[str, ColumnDef],
    output_path: Path
) -> None:
    """
    Builds a cross-source Gold table by joining multiple slices on date.
    Enforces the Join Safety Rule: slices must be explicitly filtered before joining.
    """
    print(f"Building {table_name}...")
    
    # Ensure date is datetime
    if not pd.api.types.is_datetime64_any_dtype(obs_df['date']):
        obs_df['date'] = pd.to_datetime(obs_df['date'])
        
    final_df = None
    
    for col_name, col_def in columns_config.items():
        # Filter by series_id. An explicit Gold dependency must be reviewed.
        slice_df = obs_df[obs_df['series_id'] == col_def.series_id].copy()
        if slice_df.empty:
            raise ValueError(f"Gold review guard: {table_name}.{col_name} requires reviewed series {col_def.series_id}")
        
        # Filter by dimension if specified
        if col_def.dim_key is not None and col_def.dim_value is not None:
            # Check dims (stored as JSON string)
            def match_dim(d_str):
                try:
                    d = json.loads(d_str)
                    return d.get(col_def.dim_key) == col_def.dim_value
                except:
                    return False
            slice_df = slice_df[slice_df['dims'].apply(match_dim)]
        
        # Select date and value, rename value to our target column name
        slice_df = slice_df[['date', 'value']].rename(columns={'value': col_name})
        
        # Assert one row per date for this slice before join
        if not slice_df['date'].is_unique:
            raise ValueError(f"Join Safety Violation: slice for {col_name} ({col_def.series_id}) contains multiple rows per date!")
            
        if final_df is None:
            final_df = slice_df
        else:
            final_df = final_df.merge(slice_df, on='date', how='outer')
            
    # Final check on uniqueness
    if not final_df['date'].is_unique:
        raise ValueError(f"Join Safety Violation: {table_name} contains multiple rows per date after joining!")
        
    # Sort by date
    final_df.sort_values('date', inplace=True)
    final_df.reset_index(drop=True, inplace=True)
    
    print(f"Writing {len(final_df)} rows to {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    final_df.to_parquet(output_path, index=False)


def build_all_cross_source(aligned_obs_path: Path, gold_dir: Path) -> None:
    print("Reading aligned observations...")
    obs_df = pd.read_parquet(aligned_obs_path)
    meta_df = pd.read_parquet(aligned_obs_path.parent / "series_metadata.parquet")
    reviewed_ids = reviewed_series_ids(meta_df)
    obs_df = obs_df[obs_df["series_id"].isin(reviewed_ids)].copy()
    
    # 2. gold_housing_credit_market
    build_cross_source_gold_table(
        table_name="gold_housing_credit_market",
        obs_df=obs_df,
        columns_config={
            "konut_kredisi_hacmi_tp": ColumnDef("BDDK_MONTHLY:tuketici_kredileri:tuketici_kredileri_konut", "variable", "TP"),
            "konut_kredisi_hacmi_yp": ColumnDef("BDDK_MONTHLY:tuketici_kredileri:tuketici_kredileri_konut", "variable", "YP"),
            "konut_kredisi_hacmi_toplam": ColumnDef("BDDK_MONTHLY:tuketici_kredileri:tuketici_kredileri_konut", "variable", "Toplam"),
            "konut_kredisi_faiz_orani": ColumnDef("EVDS:TP.KTF12"),
            "konut_fiyat_endeksi": ColumnDef("EVDS:TP.KFE.TR"),
            "toplam_konut_satisi": ColumnDef("EVDS:TP.AKONUTSAT1.KTRTOPLAM")
        },
        output_path=gold_dir / "gold_housing_credit_market.parquet"
    )
    
    # 3. gold_credit_market
    build_cross_source_gold_table(
        table_name="gold_credit_market",
        obs_df=obs_df,
        columns_config={
            "toplam_kredi_hacmi": ColumnDef("BDDK_MONTHLY:krediler:toplam_krediler", "variable", "Toplam"),
            "yurtici_toplam_kredi_hacmi_evds": ColumnDef("EVDS:TP.KREHACBS.A1"),
            "ticari_kredi_faiz_orani": ColumnDef("EVDS:TP.KTF17")
        },
        output_path=gold_dir / "gold_credit_market.parquet"
    )
    
    # 4. gold_deposit_market
    build_cross_source_gold_table(
        table_name="gold_deposit_market",
        obs_df=obs_df,
        columns_config={
            "mevduat_katilim_fonu_tp": ColumnDef("BDDK_MONTHLY:bilanco:mevduat_katilim_fonu", "variable", "TP"),
            "tl_mevduat_faiz_orani": ColumnDef("EVDS:TP.TRY.MT06")
        },
        output_path=gold_dir / "gold_deposit_market.parquet"
    )
    print("All cross-source tables built.")


if __name__ == "__main__":
    project_root = Path(__file__).parent.parent.parent.parent.parent
    aligned_obs = project_root / "data" / "aligned" / "monthly" / "observations.parquet"
    gold_dir = project_root / "data" / "gold"
    
    build_all_cross_source(aligned_obs, gold_dir)
