from sqlalchemy import MetaData, Table, Column, String, Float, Date, JSON, Text, DateTime

lakehouse_metadata = MetaData()

# ---------------------------------------------------------
# LAKEHOUSE DATA CATALOG (Meta-table for LLM & Discovery)
# ---------------------------------------------------------
lakehouse_data_catalog = Table(
    'lakehouse_data_catalog', lakehouse_metadata,
    Column('table_name', String, primary_key=True, comment="Tablonun lakehouse.duckdb içindeki adı"),
    Column('layer', String, comment="Medallion katmanı (Bronze, Silver, Aligned, Gold)"),
    Column('source_path', String, comment="Verinin fiziksel olarak bulunduğu Parquet veya kaynak yol"),
    Column('description', Text, comment="Tablonun genel içeriği ve kullanım amacı"),
    comment="Tüm Lakehouse içerisindeki tabloların haritasını ve fiziksel dosya yollarını tutan merkezi katalog."
)

# ---------------------------------------------------------
# GOLD TABLES
# ---------------------------------------------------------

gold_periodic_change = Table(
    'gold_periodic_change', lakehouse_metadata,
    Column('date', Date, primary_key=True, comment="Gözlem tarihi"),
    Column('series_id', String, primary_key=True, comment="İlgili metrik serisinin benzersiz kimliği (örn: BDDK_MONTHLY:...)"),
    Column('dims', JSON, primary_key=True, comment="Alt boyut kırılımları (JSON)"),
    Column('value', Float, comment="Gerçekleşen ham değer"),
    Column('mom_abs_change', Float, comment="Bir önceki aya göre mutlak değişim"),
    Column('mom_pct_change', Float, comment="Bir önceki aya göre yüzdesel değişim"),
    Column('yoy_abs_change', Float, comment="Bir önceki yılın aynı ayına göre mutlak değişim"),
    Column('yoy_pct_change', Float, comment="Bir önceki yılın aynı ayına göre yüzdesel değişim"),
    Column('source', String, comment="Verinin geldiği ana kaynak (Örn: EVDS)"),
    Column('nature', String, comment="Veri doğası (stock, flow, vb.)"),
    Column('unit', String, comment="Birim"),
    comment="Her bir serinin aylık ve yıllık bazdaki mutlak ve yüzdesel değişimlerini içeren ana temel metrik tablosu."
)

gold_housing_credit_market = Table(
    'gold_housing_credit_market', lakehouse_metadata,
    Column('date', Date, primary_key=True, comment="İşlem veya gözlem tarihi (Aylık frekans)"),
    Column('konut_kredisi_hacmi_tp', Float, comment="Bankacılık sektörü toplam konut kredisi hacmi (Milyon TL)"),
    Column('konut_kredisi_faiz_orani', Float, comment="Konut kredilerine uygulanan ağırlıklı ortalama faiz oranı (%)"),
    Column('konut_fiyat_endeksi', Float, comment="Konut Fiyat Endeksi (KFE)"),
    Column('toplam_konut_satisi', Float, comment="Türkiye geneli satılan toplam konut sayısı (Adet)"),
    comment="Konut ve gayrimenkul piyasasına dair kredi, satış ve faiz verilerini aynı tarihte hizalayarak birleştiren çapraz kaynak tablosu."
)

gold_credit_market = Table(
    'gold_credit_market', lakehouse_metadata,
    Column('date', Date, primary_key=True, comment="Gözlem tarihi (Aylık frekans)"),
    Column('toplam_kredi_hacmi', Float, comment="Bankacılık sektörü toplam kredi hacmi (Milyon TL)"),
    Column('yurtici_toplam_kredi_hacmi_evds', Float, comment="EVDS kaynaklı yurtiçi toplam kredi hacmi"),
    Column('ticari_kredi_faiz_orani', Float, comment="Ticari kredilere uygulanan ağırlıklı ortalama faiz oranı (%)"),
    comment="Genel kredi piyasasının hacmini ve ticari faiz oranlarını birleştiren analitik tablo."
)

gold_deposit_market = Table(
    'gold_deposit_market', lakehouse_metadata,
    Column('date', Date, primary_key=True, comment="Gözlem tarihi (Aylık frekans)"),
    Column('mevduat_katilim_fonu_tp', Float, comment="Mevduat ve Katılım Fonu toplam hacmi (Milyon TL)"),
    Column('tl_mevduat_faiz_orani', Float, comment="TL mevduatlara uygulanan ağırlıklı ortalama faiz oranı (%)"),
    comment="Mevduat piyasasının büyüklüğünü ve uygulanan faiz oranlarını birleştiren analitik tablo."
)

gold_precious_metal_ratios_daily = Table(
    'gold_precious_metal_ratios_daily', lakehouse_metadata,
    Column('date', Date, primary_key=True, comment="İşlem tarihi (Günlük)"),
    Column('gold_usd_ons_close', Float, comment="BIST Altın USD/Ons günlük kapanış fiyatı"),
    Column('silver_usd_ons_close', Float, comment="BIST Gümüş USD/Ons günlük kapanış fiyatı"),
    Column('gold_silver_ratio', Float, comment="Günlük Altın/Gümüş Rasyosu (Gold / Silver)"),
    comment="Günlük kapanış fiyatları üzerinden hesaplanan yüksek frekanslı Altın/Gümüş rasyosu tablosu."
)

gold_precious_metal_ratios_monthly = Table(
    'gold_precious_metal_ratios_monthly', lakehouse_metadata,
    Column('date', Date, primary_key=True, comment="Gözlem tarihi (Ay sonu bazlı)"),
    Column('gold_usd_ons_close', Float, comment="Aylık ortalama Altın USD/Ons fiyatı"),
    Column('silver_usd_ons_close', Float, comment="Aylık ortalama Gümüş USD/Ons fiyatı"),
    Column('gold_silver_ratio', Float, comment="Aylık ortalama Altın/Gümüş Rasyosu (Günlük rasyoların ortalamasıdır, ortalamaların birbirine bölümü DEĞİLDİR)"),
    Column('gold_mom_pct_change', Float, comment="Altın fiyatındaki aylık yüzdesel değişim"),
    Column('silver_mom_pct_change', Float, comment="Gümüş fiyatındaki aylık yüzdesel değişim"),
    Column('ratio_mom_pct_change', Float, comment="Altın/Gümüş rasyosundaki aylık yüzdesel değişim"),
    comment="Günlük bazda hesaplanan Altın/Gümüş rasyosunun aylık ortalama ve momentum (değişim) analizi tablosu."
)

gold_finturk_province_credit_quality = Table(
    'gold_finturk_province_credit_quality', lakehouse_metadata,
    Column('date', Date, primary_key=True, comment="Gözlem tarihi (Çeyreklik frekans)"),
    Column('province', String, primary_key=True, comment="İl Adı (geo_level=province)"),
    Column('geo_level', String, comment="Coğrafi kırılım seviyesi (province, country vb.)"),
    Column('plate_code', String, comment="İl plaka kodu"),
    Column('total_cash_loans', Float, comment="İldeki toplam nakdi krediler hacmi (Milyon TL)"),
    Column('nonperforming_receivables', Float, comment="İldeki toplam takipteki alacaklar (NPL) hacmi (Milyon TL)"),
    Column('npl_ratio', Float, comment="Takibe dönüşüm oranı (NPL Ratio = Takipteki Alacaklar / Toplam Nakdi Kredi + Takipteki Alacaklar)"),
    Column('housing_loans', Float, comment="İldeki konut kredisi hacmi (Milyon TL, veri mevcutsa)"),
    comment="BDDK FinTürk verisinden derlenen, il bazlı kredi hacmi ve risk (NPL) oranlarını çeyreklik bazda sunan coğrafi tablo."
)

gold_series_evidence = Table(
    'gold_series_evidence', lakehouse_metadata,
    Column('gold_table', String, primary_key=True, comment="Gold tablosunun adı"),
    Column('gold_column', String, primary_key=True, comment="Gold tablosundaki üretilmiş kolonun adı"),
    Column('source_series_id', String, comment="Dayandığı ham verinin (Silver/Aligned) seri kimliği"),
    Column('source', String, comment="Veri kaynağı (EVDS, BDDK_MONTHLY vb.)"),
    Column('source_freq', String, comment="Ham verinin frekansı (M, Q, D)"),
    Column('source_nature', String, comment="Verinin doğası (stock, flow, price, rate)"),
    Column('alignment_method', String, comment="Veri birleştirilirken kullanılan hizalama yöntemi (last, mean, sum vb.)"),
    Column('dimension_filter', String, comment="Filtrelemede kullanılan boyut (dimension) kısıtı (Örn: variable=TP)"),
    Column('transformation', String, comment="Yapılan matematiksel veya iş mantığı dönüşümü"),
    Column('semantic_description', Text, comment="Kolonun anlamsal (iş birimi) açıklaması"),
    comment="Gold tablolarındaki her bir sütunun tam olarak hangi kaynaktan, hangi filtre ve formülle (lineage) geldiğini belgeleyen Data Lineage / Kanıt tablosu."
)
