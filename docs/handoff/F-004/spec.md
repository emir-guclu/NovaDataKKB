# F-004: Gold Katmanı (Semantic Layer, Feature Store & Panel Veri) Şartnamesi

> **Kapsam:** Bu doküman, F-004 aşamasında kurulacak olan **Gold Katmanı** veri mimarisini, DuckDB sıfır kopyalı view (Semantic Gateway) modelini, aylık panel veri şemasını ve analitik türetilmiş özellikler (Feature Store) tasarımını tanımlar.

---

## 1. Mimari Şema ve Katmanlar Arası İlişki

Gold katmanı, fiziksel veri kopyalamak yerine **tek bir isim alanı (`gold.*`)** altında hizmet veren bir anlamsal kapı (Semantic Gateway) ve analitik özellik deposu olarak çalışır:

```text
[Ham Veri Kaynakları] 
         │
         ▼
[data/silver/silver.duckdb] (Fiziksel Tablo - Ham D/W/M/Q Frekanslar)
         │
         ▼ (Zaman Hizalama Kuralları: mean, last, native, quarter_end_sparse)
[data/aligned/monthly/aligned.duckdb] (Fiziksel Tablo - Ortak Aylık Eksen)
         │
         ▼ (Sıfır Kopyalı ATTACH + VIEW Kapıları)
┌──────────────────────────── [data/gold/gold.duckdb] ────────────────────────────┐
│                                                                                 │
│  1. VIEW: gold.observations_native ───> silver.duckdb'deki ham gözlemler        │
│     • Rolü: Günlük kur, cuma bakiye gibi nokta atışı sorgular için              │
│     • Maliyet: 0 byte (Zero-Copy)                                               │
│                                                                                 │
│  2. VIEW: gold.panel_monthly       ───> aligned.duckdb'deki aylık gözlemler     │
│     • Rolü: İki kaynağı karşılaştıran makro, trend ve korelasyon analizleri     │
│     • Maliyet: 0 byte (Zero-Copy)                                               │
│                                                                                 │
│  3. VIEW: gold.series_metadata     ───> Ortak seri boyut kataloğu               │
│     • Rolü: Seri adları, birimleri, açıklamaları ve frekans metadatası          │
│     • Maliyet: 0 byte (Zero-Copy)                                               │
│                                                                                 │
│  ─────────────────────────────────────────────────────────────────────────────  │
│                                                                                 │
│  4. TABLO (Fiziksel): gold.features_monthly (Analitik Feature Store)           │
│     • Rolü: Aylık panel üzerinden hesaplanan türetilmiş finansal göstergeler:   │
│       - Aylık ve Yıllık Büyüme Oranları (MoM, YoY % değişim)                    │
│       - Finansal Rasyolar (NPL Oranı = Takipteki / Toplam Kredi vb.)           │
│       - Gecikmeli Değişkenler (lag_1, lag_3, lag_12 faiz/enflasyon etkileri)   │
└─────────────────────────────────────────────────────────────────────────────────┘
                                 ▲
                                 │ Tek Şema Sorgulama (gold.*)
                     [LLM Ajanı & sql_query Tool]
```

---

## 2. Neden Bu Tasarım Seçildi? (Tasarım Gerekçeleri)

1. **Tek İsim Alanı (`gold.*`) ile Düşük Halüsinasyon:**
   - LLM'e `silver.*` ve `gold.*` şeklinde 2 farklı veritabanı şeması ve karar kuralları vermek yerine, yalnızca `gold.*` şeması sunulur.
   - LLM sorgu üretirken "Hangi veritabanına bağlansam?" karmaşası yaşamaz; yalnızca "Nokta sorgusu ise `observations_native`, trend/panel ise `panel_monthly`" ayrımını yapar.
2. **`sqlglot` Allowlist Güvenliği:**
   - PDF şartnamesindeki `ALLOWLIST = {"gold", "session"}` kuralı bozulmaz, Silver'a ayrı bir güvenlik deliği açılmaz.
3. **Sıfır Depolama ve Sıfır Senkronizasyon (Zero-Copy):**
   - 450.000 satırlık veriyi üçüncü kez diske kopyalamayız. Silver veya Aligned güncellendiğinde Gold view'ları anında güncel veriyi gösterir.

---

## 3. Tablo ve View Tanımları

### A. `gold.observations_native` (View)
* **Hedef:** `data/silver/silver.duckdb` içindeki `observations` tablosu.
* **Kullanım Senaryosu:** Günlük döviz kuru kapanışları, haftalık bankacılık bülteni detayları gibi ham frekans gerektiren nokta atışı sorular.

### B. `gold.panel_monthly` (View)
* **Hedef:** `data/aligned/monthly/aligned.duckdb` içindeki `observations` tablosu.
* **Kullanım Senaryosu:** Kurlar, krediler, enflasyon ve mevduatın aynı ay sonu ekseninde karşılaştırıldığı makro analizler.

### C. `gold.series_metadata` (View)
* **Hedef:** `data/aligned/monthly/aligned.duckdb` içindeki `series_metadata` tablosu.
* **Kullanım Senaryosu:** Serilerin Türkçe adı, birimi, kaynak sistemi ve frekans açıklamaları.

### D. `gold.features_monthly` (Fiziksel Analitik Tablo)
* **Hedef:** `data/gold/gold.duckdb` içinde kalıcı fiziksel tablo.
* **Hesaplanan Özellikler:**
  1. `kredi_toplam_stok_mom_pct`: Aylık kredi büyüme oranı.
  2. `kredi_toplam_stok_yoy_pct`: Yıllık kredi büyüme oranı.
  3. `npl_ratio`: Takipteki alacaklar / Toplam krediler rasyosu.
  4. `usd_try_mom_pct`: Dolar kurunun aylık değişim hızı.
  5. `politika_faizi_lag1`: 1 ay önceki fonlama faiz maliyeti.
  6. `tufe_yillik_degisim`: Yıllık enflasyon oranı.

---

## 4. Uygulama Adımları (Checklist)

- [ ] **Adım 1:** `backend/scripts/build_gold.py` scriptinin yazılması.
  - `gold.duckdb` oluşturulup `silver_db` ve `aligned_db`'ye `ATTACH` edilmesi.
  - View'ların tanımlanması.
- [ ] **Adım 2:** Analitik feature motorunun kodlanması (`features_monthly` hesaplama SQL/Python pipeline).
- [ ] **Adım 3:** `backend/tests/test_gold.py` test paketinin yazılması.
  - View'ların veri döndürdüğünün doğrulanması.
  - Rasyoların matematiksel tutarlılığının (örn. NPL oranı %0-%100 aralığında mı) test edilmesi.
- [ ] **Adım 4:** `SETUP.md` dosyasında Gold katmanı komutlarının belgelenmesi.
