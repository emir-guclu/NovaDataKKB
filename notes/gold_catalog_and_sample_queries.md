# Gold Layer Catalog & Sample Queries

## Catalog Descriptions

| Table Name | Description |
|---|---|
| `gold_periodic_change` | Her bir serinin aylık ve yıllık mutlak (absolute) ve oransal (percentage) değişimlerini içeren ana metriği tablosu. Diğer tüm Gold tabloları bu değişim metriklerini kullanabilir. |
| `gold_housing_credit_market` | Konut kredisi hacmi, konut kredisi faiz oranı, konut fiyat endeksi ve toplam konut satışı verilerini aylık frekansta birleştiren gayrimenkul ve konut kredisi piyasası tablosu. |
| `gold_credit_market` | Yurtiçi toplam kredi hacmi, bankacılık sektörü toplam kredi hacmi ve ticari kredi faiz oranlarını aylık frekansta birleştiren genel kredi piyasası tablosu. |
| `gold_deposit_market` | Bankacılık sektörü mevduat/katılım fonu hacmi ile TL mevduat faiz oranlarını aylık frekansta birleştiren mevduat piyasası tablosu. |
| `gold_precious_metal_ratios_daily` | Altın ve Gümüş'ün BIST kapanış fiyatlarını kullanarak oluşturulan günlük altın/gümüş rasyosu tablosu. Hesaplama ortalamalar üzerinden değil, her bir ortak işlem günündeki gerçek kapanışlar üzerinden hesaplanmıştır. |
| `gold_finturk_province_credit_quality` | FinTürk il bazlı nakdi krediler, takipteki alacaklar ve NPL (takibe dönüşüm) oranını çeyreklik frekansta sunan coğrafi kredi kalitesi tablosu. |
| `gold_series_evidence` | Tüm Gold kolonlarının hangi Silver/Aligned kaynak serilerden, hangi boyut filtresinden (dimension) ve hangi hizalama yöntemiyle (alignment method) hesaplandığını belgeleyen kanıt (provenance) tablosu. |
| `gold_evds_catalog` | Agent'ın EVDS sisteminde bulunan serileri (isim, kategori, frekans) sorgulayabilmesi ve henüz sisteme alınmamış serileri on-demand olarak yükleyebilmesi için oluşturulmuş katalog keşif view'ı. |

## Sample Queries

### Soru 1: Konut kredisi faiz oranlarının artış trendinde olduğu dönemlerde konut satışları ve konut kredisi hacmi nasıl etkilenmiştir?
```sql
SELECT 
    date,
    konut_kredisi_faiz_orani,
    toplam_konut_satisi,
    konut_kredisi_hacmi_tp
FROM gold_housing_credit_market
WHERE date >= '2023-01-01'
ORDER BY date ASC;
```

### Soru 2: Ticari kredi faiz oranlarının son 1 yıldaki gelişimi ile toplam kredi hacmi arasındaki ilişki nedir?
```sql
SELECT 
    cm.date,
    cm.ticari_kredi_faiz_orani,
    cm.toplam_kredi_hacmi,
    pc.mom_pct_change as kredi_hacmi_aylik_degisim_orani
FROM gold_credit_market cm
LEFT JOIN gold_periodic_change pc 
  ON cm.date = pc.date 
  AND pc.series_id = 'BDDK_MONTHLY:krediler:toplam_krediler'
  AND pc.dims = '{"variable": "Toplam"}'
WHERE cm.date >= '2023-06-01'
ORDER BY cm.date ASC;
```

### Soru 3: En son çeyrekte NPL (Takibe Dönüşüm Oranı) en yüksek olan ilk 5 il hangileridir?
```sql
SELECT 
    province, 
    date, 
    npl_ratio, 
    total_cash_loans, 
    nonperforming_receivables
FROM gold_finturk_province_credit_quality
WHERE date = (SELECT MAX(date) FROM gold_finturk_province_credit_quality)
  AND geo_level = 'province'
ORDER BY npl_ratio DESC
LIMIT 5;
```

### Soru 4: Son ayın ortalama Altın/Gümüş oranındaki değişim nedir?
```sql
SELECT 
    date,
    gold_usd_ons_close,
    silver_usd_ons_close,
    gold_silver_ratio,
    ratio_mom_pct_change
FROM gold_precious_metal_ratios_monthly
ORDER BY date DESC
LIMIT 1;
```
