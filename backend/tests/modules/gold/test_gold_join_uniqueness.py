import pytest
import pandas as pd
from pathlib import Path

# Proje root dizinini bul
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.parent
GOLD_DIR = PROJECT_ROOT / "data" / "gold"

CROSS_SOURCE_TABLES = [
    "gold_housing_credit_market",
    "gold_credit_market",
    "gold_deposit_market"
]

@pytest.mark.parametrize("table_name", CROSS_SOURCE_TABLES)
def test_gold_table_join_uniqueness(table_name):
    """
    Her cross-source Gold tablosunun her bir tarih için tam olarak 
    tek bir satır (row) ürettiğini doğrular. BDDK ve EVDS verilerinin 
    doğru dimension slice kullanılarak join edilmesini güvence altına alır.
    """
    parquet_path = GOLD_DIR / f"{table_name}.parquet"
    
    # Dosya yoksa test fail olsun (TDD mantığı gereği fail ile başlar)
    assert parquet_path.exists(), f"{table_name}.parquet henüz oluşturulmamış!"
    
    df = pd.read_parquet(parquet_path)
    
    # Tablonun en az bir veri içerdiğinden emin olalım
    assert not df.empty, f"{table_name} boş olamaz."
    
    # date kolonu bulunmalı
    assert "date" in df.columns, f"{table_name} 'date' kolonu içermeli."
    
    # date kolonundaki değerler unique (benzersiz) olmalı
    # Eğer toplam satır sayısı, eşsiz tarih sayısına eşitse = her tarihten 1 tane var
    assert len(df) == df["date"].nunique(), f"Join Hatası: {table_name} tablosunda ayni tarihe (date) ait birden fazla satır var. Join işlemi dimension filter uygulanmadan yapılmış olabilir!"
