# Veritabanı Tanımları

> Bu dosya `scripts/generate_db_docs.py` ile koddan otomatik üretilir.
> Elle düzenlemeyin; şema değişince script'i tekrar çalıştırın.

## Lakehouse Tabloları (Gold ve Katalog)


### `gold_credit_market`

Genel kredi piyasasının hacmini ve ticari faiz oranlarını birleştiren analitik tablo.


| Kolon | Tip | Açıklama |
|---|---|---|
| `date` 🔑 | DATE | Gözlem tarihi (Aylık frekans) |
| `toplam_kredi_hacmi` | FLOAT | Bankacılık sektörü toplam kredi hacmi (Milyon TL) |
| `yurtici_toplam_kredi_hacmi_evds` | FLOAT | EVDS kaynaklı yurtiçi toplam kredi hacmi |
| `ticari_kredi_faiz_orani` | FLOAT | Ticari kredilere uygulanan ağırlıklı ortalama faiz oranı (%) |

### `gold_deposit_market`

Mevduat piyasasının büyüklüğünü ve uygulanan faiz oranlarını birleştiren analitik tablo.


| Kolon | Tip | Açıklama |
|---|---|---|
| `date` 🔑 | DATE | Gözlem tarihi (Aylık frekans) |
| `mevduat_katilim_fonu_tp` | FLOAT | Mevduat ve Katılım Fonu toplam hacmi (Milyon TL) |
| `tl_mevduat_faiz_orani` | FLOAT | TL mevduatlara uygulanan ağırlıklı ortalama faiz oranı (%) |

### `gold_finturk_province_credit_quality`

BDDK FinTürk verisinden derlenen, il bazlı kredi hacmi ve risk (NPL) oranlarını çeyreklik bazda sunan coğrafi tablo.


| Kolon | Tip | Açıklama |
|---|---|---|
| `date` 🔑 | DATE | Gözlem tarihi (Çeyreklik frekans) |
| `province` 🔑 | VARCHAR | İl Adı (geo_level=province) |
| `geo_level` | VARCHAR | Coğrafi kırılım seviyesi (province, country vb.) |
| `plate_code` | VARCHAR | İl plaka kodu |
| `total_cash_loans` | FLOAT | İldeki toplam nakdi krediler hacmi (Bin TL) |
| `nonperforming_receivables` | FLOAT | İldeki toplam takipteki alacaklar (NPL) hacmi (Bin TL) |
| `npl_ratio` | FLOAT | Takibe dönüşüm oranı (NPL Ratio = Takipteki Alacaklar / (Toplam Nakdi Kredi + Takipteki Alacaklar)) |
| `housing_loans` | FLOAT | İldeki konut kredisi hacmi (Bin TL, veri mevcutsa) |

### `gold_housing_credit_market`

Konut ve gayrimenkul piyasasına dair kredi, satış ve faiz verilerini aynı tarihte hizalayarak birleştiren çapraz kaynak tablosu.


| Kolon | Tip | Açıklama |
|---|---|---|
| `date` 🔑 | DATE | İşlem veya gözlem tarihi (Aylık frekans) |
| `konut_kredisi_hacmi_tp` | FLOAT | Bankacılık sektörü toplam konut kredisi hacmi (Milyon TL) |
| `konut_kredisi_faiz_orani` | FLOAT | Konut kredilerine uygulanan ağırlıklı ortalama faiz oranı (%) |
| `konut_fiyat_endeksi` | FLOAT | Konut Fiyat Endeksi (KFE) |
| `toplam_konut_satisi` | FLOAT | Türkiye geneli satılan toplam konut sayısı (Adet) |

### `gold_periodic_change`

Her bir serinin aylık ve yıllık bazdaki mutlak ve yüzdesel değişimlerini içeren ana temel metrik tablosu.


| Kolon | Tip | Açıklama |
|---|---|---|
| `date` 🔑 | DATE | Gözlem tarihi |
| `series_id` 🔑 | VARCHAR | İlgili metrik serisinin benzersiz kimliği (örn: BDDK_MONTHLY:...) |
| `dims` 🔑 | JSON | Alt boyut kırılımları (JSON) |
| `value` | FLOAT | Gerçekleşen ham değer |
| `mom_abs_change` | FLOAT | Bir önceki aya göre mutlak değişim |
| `mom_pct_change` | FLOAT | Bir önceki aya göre yüzdesel değişim |
| `yoy_abs_change` | FLOAT | Bir önceki yılın aynı ayına göre mutlak değişim |
| `yoy_pct_change` | FLOAT | Bir önceki yılın aynı ayına göre yüzdesel değişim |
| `source` | VARCHAR | Verinin geldiği ana kaynak (Örn: EVDS) |
| `nature` | VARCHAR | Veri doğası (stock, flow, vb.) |
| `unit` | VARCHAR | Birim |

### `gold_precious_metal_ratios_daily`

Günlük kapanış fiyatları üzerinden hesaplanan yüksek frekanslı Altın/Gümüş rasyosu tablosu.


| Kolon | Tip | Açıklama |
|---|---|---|
| `date` 🔑 | DATE | İşlem tarihi (Günlük) |
| `gold_usd_ons_close` | FLOAT | BIST Altın USD/Ons günlük kapanış fiyatı |
| `silver_usd_ons_close` | FLOAT | BIST Gümüş USD/Ons günlük kapanış fiyatı |
| `gold_silver_ratio` | FLOAT | Günlük Altın/Gümüş Rasyosu (Gold / Silver) |

### `gold_precious_metal_ratios_monthly`

Günlük bazda hesaplanan Altın/Gümüş rasyosunun aylık ortalama ve momentum (değişim) analizi tablosu.


| Kolon | Tip | Açıklama |
|---|---|---|
| `date` 🔑 | DATE | Gözlem tarihi (Ay sonu bazlı) |
| `gold_usd_ons_close` | FLOAT | Aylık ortalama Altın USD/Ons fiyatı |
| `silver_usd_ons_close` | FLOAT | Aylık ortalama Gümüş USD/Ons fiyatı |
| `gold_silver_ratio` | FLOAT | Aylık ortalama Altın/Gümüş Rasyosu (Günlük rasyoların ortalamasıdır, ortalamaların birbirine bölümü DEĞİLDİR) |
| `gold_mom_pct_change` | FLOAT | Altın fiyatındaki aylık yüzdesel değişim |
| `silver_mom_pct_change` | FLOAT | Gümüş fiyatındaki aylık yüzdesel değişim |
| `ratio_mom_pct_change` | FLOAT | Altın/Gümüş rasyosundaki aylık yüzdesel değişim |

### `gold_series_evidence`

Gold tablolarındaki her bir sütunun tam olarak hangi kaynaktan, hangi filtre ve formülle (lineage) geldiğini belgeleyen Data Lineage / Kanıt tablosu.


| Kolon | Tip | Açıklama |
|---|---|---|
| `gold_table` 🔑 | VARCHAR | Gold tablosunun adı |
| `gold_column` 🔑 | VARCHAR | Gold tablosundaki üretilmiş kolonun adı |
| `source_series_id` | VARCHAR | Dayandığı ham verinin (Silver/Aligned) seri kimliği |
| `source` | VARCHAR | Veri kaynağı (EVDS, BDDK_MONTHLY vb.) |
| `source_freq` | VARCHAR | Ham verinin frekansı (M, Q, D) |
| `source_nature` | VARCHAR | Verinin doğası (stock, flow, price, rate) |
| `alignment_method` | VARCHAR | Veri birleştirilirken kullanılan hizalama yöntemi (last, mean, sum vb.) |
| `dimension_filter` | VARCHAR | Filtrelemede kullanılan boyut (dimension) kısıtı (Örn: variable=TP) |
| `transformation` | VARCHAR | Yapılan matematiksel veya iş mantığı dönüşümü |
| `semantic_description` | TEXT | Kolonun anlamsal (iş birimi) açıklaması |

### `lakehouse_data_catalog`

Tüm Lakehouse içerisindeki tabloların haritasını ve fiziksel dosya yollarını tutan merkezi katalog.


| Kolon | Tip | Açıklama |
|---|---|---|
| `table_name` 🔑 | VARCHAR | Tablonun lakehouse.duckdb içindeki adı |
| `layer` | VARCHAR | Medallion katmanı (Bronze, Silver, Aligned, Gold) |
| `source_path` | VARCHAR | Verinin fiziksel olarak bulunduğu Parquet veya kaynak yol |
| `description` | TEXT | Tablonun genel içeriği ve kullanım amacı |

## Canonical Silver Şeması

Kaynaktan bağımsız ortak sözleşme (`backend/app/models/silver_canonical.py`). Doğrulama kuralları Pydantic validator'larıyla uygulanır.


### `CanonicalObservation`

Canonical cross-source Silver observation.


| Alan | Tip | Zorunlu | Varsayılan |
|---|---|---|---|
| `series_id` | `str` | evet | — |
| `source` | `str` | evet | — |
| `date` | `date` | evet | — |
| `period_start` | `date` | evet | — |
| `period_end` | `date` | evet | — |
| `value` | `float \| None` | hayır | `None` |
| `freq` | `str` | evet | — |
| `unit` | `str \| None` | hayır | `None` |
| `dims` | `dict[str, Any]` | hayır | `dict()` |
| `source_file` | `str \| None` | hayır | `None` |

### `CanonicalSeriesMetadata`

Canonical cross-source series metadata.


| Alan | Tip | Zorunlu | Varsayılan |
|---|---|---|---|
| `series_id` | `str` | evet | — |
| `source` | `str` | evet | — |
| `series_code` | `str \| None` | hayır | `None` |
| `series_name` | `str` | evet | — |
| `category` | `str` | evet | — |
| `freq` | `str` | evet | — |
| `unit` | `str \| None` | hayır | `None` |
| `description` | `str \| None` | hayır | `None` |
| `tags` | `list[str]` | hayır | `list()` |
| `accumulation` | `str` | hayır | `'none'` |
| `is_cumulative` | `bool` | hayır | `False` |
| `nature` | `str` | evet | — |
| `nature_reviewed` | `bool` | hayır | `False` |
| `alignment_override` | `str \| None` | hayır | `None` |

### İzin Verilen Değerler

| Sabit | Değerler |
|---|---|
| `VALID_FREQS` | `D`, `M`, `Q`, `W`, `Y` |
| `VALID_ACCUMULATIONS` | `none`, `since_start`, `ytd` |
| `VALID_NATURES` | `flow`, `price`, `rate`, `stock`, `unclassified` |
| `VALID_ALIGNMENT_OVERRIDES` | `last`, `mean`, `sum` |
