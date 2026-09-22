import pandas as pd
from pathlib import Path

def build_gold_evidence(gold_dir: Path) -> None:
    """
    Builds the gold_series_evidence provenance table.
    Tracks which Gold columns originate from which Silver/Aligned series.
    """
    print("Building gold_series_evidence...")
    
    evidence_data = [
        # 1. gold_periodic_change
        {
            "gold_table": "gold_periodic_change",
            "gold_column": "mom_pct_change",
            "source_series_id": "*",
            "source": "Aligned",
            "source_freq": "M",
            "source_nature": "Inherited",
            "alignment_method": "Inherited",
            "dimension_filter": "Inherited",
            "transformation": "1-month percentage change (value - shift(1))/abs(shift(1))",
            "semantic_description": "Month-over-month percentage change"
        },
        
        # 2. gold_housing_credit_market
        {
            "gold_table": "gold_housing_credit_market",
            "gold_column": "konut_kredisi_hacmi_tp",
            "source_series_id": "BDDK_MONTHLY:tuketici_kredileri:tuketici_kredileri_konut",
            "source": "BDDK_MONTHLY",
            "source_freq": "M",
            "source_nature": "stock",
            "alignment_method": "last",
            "dimension_filter": '{"variable": "TP"}',
            "transformation": "None",
            "semantic_description": "Total housing loans in TRY"
        },
        {
            "gold_table": "gold_housing_credit_market",
            "gold_column": "konut_kredisi_hacmi_yp",
            "source_series_id": "BDDK_MONTHLY:tuketici_kredileri:tuketici_kredileri_konut",
            "source": "BDDK_MONTHLY",
            "source_freq": "M",
            "source_nature": "stock",
            "alignment_method": "last",
            "dimension_filter": '{"variable": "YP"}',
            "transformation": "None",
            "semantic_description": "Total housing loans in Foreign Currency (FX/YP)"
        },
        {
            "gold_table": "gold_housing_credit_market",
            "gold_column": "konut_kredisi_hacmi_toplam",
            "source_series_id": "BDDK_MONTHLY:tuketici_kredileri:tuketici_kredileri_konut",
            "source": "BDDK_MONTHLY",
            "source_freq": "M",
            "source_nature": "stock",
            "alignment_method": "last",
            "dimension_filter": '{"variable": "Toplam"}',
            "transformation": "None",
            "semantic_description": "Total housing loans (TRY + FX)"
        },
        {
            "gold_table": "gold_housing_credit_market",
            "gold_column": "konut_kredisi_faiz_orani",
            "source_series_id": "EVDS:TP.KTF12",
            "source": "EVDS",
            "source_freq": "W",
            "source_nature": "rate",
            "alignment_method": "mean",
            "dimension_filter": "None",
            "transformation": "None",
            "semantic_description": "Housing loan weighted average interest rate"
        },
        {
            "gold_table": "gold_housing_credit_market",
            "gold_column": "konut_fiyat_endeksi",
            "source_series_id": "EVDS:TP.KFE.TR",
            "source": "EVDS",
            "source_freq": "M",
            "source_nature": "price",
            "alignment_method": "last",
            "dimension_filter": "None",
            "transformation": "None",
            "semantic_description": "Housing price index"
        },
        {
            "gold_table": "gold_housing_credit_market",
            "gold_column": "toplam_konut_satisi",
            "source_series_id": "EVDS:TP.AKONUTSAT1.KTRTOPLAM",
            "source": "EVDS",
            "source_freq": "M",
            "source_nature": "flow",
            "alignment_method": "sum",
            "dimension_filter": "None",
            "transformation": "None",
            "semantic_description": "Total housing sales units"
        },
        
        # 3. gold_credit_market
        {
            "gold_table": "gold_credit_market",
            "gold_column": "toplam_kredi_hacmi",
            "source_series_id": "BDDK_MONTHLY:krediler:toplam_krediler",
            "source": "BDDK_MONTHLY",
            "source_freq": "M",
            "source_nature": "stock",
            "alignment_method": "last",
            "dimension_filter": '{"variable": "Toplam"}',
            "transformation": "None",
            "semantic_description": "Total loans across all types"
        },
        {
            "gold_table": "gold_credit_market",
            "gold_column": "yurtici_toplam_kredi_hacmi_evds",
            "source_series_id": "EVDS:TP.KREHACBS.A1",
            "source": "EVDS",
            "source_freq": "W",
            "source_nature": "stock",
            "alignment_method": "last",
            "dimension_filter": "None",
            "transformation": "None",
            "semantic_description": "Total domestic credit volume (EVDS)"
        },
        {
            "gold_table": "gold_credit_market",
            "gold_column": "ticari_kredi_faiz_orani",
            "source_series_id": "EVDS:TP.KTF17",
            "source": "EVDS",
            "source_freq": "W",
            "source_nature": "rate",
            "alignment_method": "mean",
            "dimension_filter": "None",
            "transformation": "None",
            "semantic_description": "Commercial loan interest rate"
        },
        
        # 4. gold_deposit_market
        {
            "gold_table": "gold_deposit_market",
            "gold_column": "mevduat_katilim_fonu_tp",
            "source_series_id": "BDDK_MONTHLY:bilanco:mevduat_katilim_fonu",
            "source": "BDDK_MONTHLY",
            "source_freq": "M",
            "source_nature": "stock",
            "alignment_method": "last",
            "dimension_filter": '{"variable": "TP"}',
            "transformation": "None",
            "semantic_description": "Total deposits and participation funds in TRY"
        },
        {
            "gold_table": "gold_deposit_market",
            "gold_column": "tl_mevduat_faiz_orani",
            "source_series_id": "EVDS:TP.TRY.MT06",
            "source": "EVDS",
            "source_freq": "W",
            "source_nature": "rate",
            "alignment_method": "mean",
            "dimension_filter": "None",
            "transformation": "None",
            "semantic_description": "Total TL deposit interest rate"
        },
        
        # 5. gold_precious_metal_ratios
        {
            "gold_table": "gold_precious_metal_ratios",
            "gold_column": "gold_silver_ratio",
            "source_series_id": "EVDS:TP.ALTINPIYASA.KAP03, EVDS:TP.GUMUSPIYASA.KAP03",
            "source": "EVDS",
            "source_freq": "D",
            "source_nature": "price",
            "alignment_method": "Direct from Silver",
            "dimension_filter": "None",
            "transformation": "gold_usd_ons_close / silver_usd_ons_close (daily ratio)",
            "semantic_description": "Gold/Silver price ratio based on daily closing prices"
        },
        
        # 6. gold_finturk_province_credit_quality
        {
            "gold_table": "gold_finturk_province_credit_quality",
            "gold_column": "total_cash_loans",
            "source_series_id": "BDDK_FINTURK:t1:nakdikrediler",
            "source": "BDDK_FINTURK",
            "source_freq": "Q",
            "source_nature": "stock",
            "alignment_method": "sparse",
            "dimension_filter": 'geo_level=province',
            "transformation": "None",
            "semantic_description": "Total cash loans per province"
        },
        {
            "gold_table": "gold_finturk_province_credit_quality",
            "gold_column": "npl_ratio",
            "source_series_id": "BDDK_FINTURK:t1:takiptekialacaklar, BDDK_FINTURK:t1:nakdikrediler",
            "source": "BDDK_FINTURK",
            "source_freq": "Q",
            "source_nature": "stock",
            "alignment_method": "sparse",
            "dimension_filter": 'geo_level=province',
            "transformation": "takipteki_alacaklar / (nakdi_krediler + takipteki_alacaklar)",
            "semantic_description": "Non-performing loan ratio per province"
        }
    ]
    
    df = pd.DataFrame(evidence_data)
    
    out_path = gold_dir / "gold_series_evidence.parquet"
    print(f"Writing {len(df)} rows to {out_path}")
    gold_dir.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path, index=False)
    print("Done.")

if __name__ == "__main__":
    project_root = Path(__file__).parent.parent.parent.parent.parent
    gold_dir = project_root / "data" / "gold"
    
    build_gold_evidence(gold_dir)
