import pytest
import pandas as pd
import numpy as np

def test_daily_ratio_vs_monthly_average_ratio():
    """
    Bu test, Gold katmanı değerli madenler tablosundaki en önemli kuralı doğrular:
    Aylık ortalama oran, 'günlük oranların aylık ortalaması' olmalıdır.
    'Aylık ortalama altın fiyatının aylık ortalama gümüş fiyatına bölümü' YANLIŞTIR.
    (avg(a) / avg(b) != avg(a / b))
    """
    
    # 3 günlük basit bir örnek veri
    data = {
        'date': pd.to_datetime(['2024-01-01', '2024-01-02', '2024-01-03']),
        'gold': [2000.0, 2100.0, 1900.0],
        'silver': [20.0, 25.0, 15.0]
    }
    df = pd.DataFrame(data)
    
    # Doğru Yöntem: Önce günlük oran hesaplanır, sonra ortalaması alınır
    df['daily_ratio'] = df['gold'] / df['silver']
    correct_monthly_ratio = df['daily_ratio'].mean()
    
    # Yanlış Yöntem: Önce altın ve gümüşün ayrı ayrı aylık ortalaması alınır, sonra bölünür
    avg_gold = df['gold'].mean()
    avg_silver = df['silver'].mean()
    wrong_monthly_ratio = avg_gold / avg_silver
    
    # Matematiksel olarak eşit olmadıklarını doğrula
    assert not np.isclose(correct_monthly_ratio, wrong_monthly_ratio), \
        "Matematiksel kural ihlali: avg(a/b) == avg(a)/avg(b) çıktı. Test verisini değiştirin."
        
    # Somut değerlerle kontrol
    # Günlük oranlar: 2000/20 = 100, 2100/25 = 84, 1900/15 = 126.666...
    # Doğru ortalama oran: (100 + 84 + 126.666...) / 3 = 103.555...
    # Yanlış ortalama: (2000+2100+1900)/3 = 2000, (20+25+15)/3 = 20, 2000/20 = 100
    
    assert np.isclose(correct_monthly_ratio, 103.55555555555556)
    assert np.isclose(wrong_monthly_ratio, 100.0)
