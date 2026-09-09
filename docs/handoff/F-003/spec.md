# F-003: EVDS Silver Katmanı — Mimari Kurallar ve Veri Modeli

> Bu doküman, **F-003 (EVDS Veri Standardizasyonu ve Normalizasyonu / Silver Katmanı)** geliştirme sürecinde uyulması zorunlu olan mimari kararları, kanonik tablo şemalarını (§5.4), veri temizleme kurallarını ve Gold katmanı (`gold.observations`) entegrasyon standartlarını tanımlar.

---

## 1. Temel Mimari İlkeler

1. **Kanonik Şema Uyumu (§5.4):** Silver katmanında üretilen gözlem tablosu, ileride BDDK ve FinTürk silver tabloları ile tek bir `gold.observations` tablosunda **`UNION ALL`** edilebilecek şekilde birebir aynı kolon adlarına, tiplerine ve standartlarına sahip olmalıdır.
2. **Kaynak Ön-Ekli `series_id` Zorunluluğu:** Orijinal EVDS kodları (`TP.DK.USD.A.YTL`) tek başına kullanılmaz; çakışmaları önlemek ve kaynağı açıkça belirtmek için **`<SOURCE>:<RAW_CODE>`** formatında (örn. `EVDS:TP.DK.USD.A.YTL`) saklanır.
3. **Kanonik Frekans Kod Seti:** Serbest metinler (`Günlük`, `Haftalık`, `DAILY`) yasaktır. Yalnızca projenin standart kod seti kullanılır: **`D` (Günlük) | `W` (Haftalık) | `M` (Aylık) | `Q` (Çeyreklik) | `Y` (Yıllık)**.
4. **Resmi Metadatadan Eşlenen Frekans (Metadata-Driven Frequency):** Manifestteki insan kaynaklı etiketlere dayanılmaz. Frekans, doğrudan TCMB'nin resmi metadatasındaki (`metadata_raw.json`) `FREQUENCY_STR` alanından kanonik kod kümesine (`D`, `W`, `M`, `Q`, `Y`) dönüştürülür ve her iki Parquet tablosuna tek merkezden yazılır.
5. **Genişletilebilirlik İçin `dims` Kolonu:** EVDS serilerinde il/şube kırılımı olmasa dahi, BDDK/FinTürk (`{"il": "Trabzon"}`) ile şema uyumsuzluğu yaşamamak için **`dims`** kolonu varsayılan boş JSON objesi (`"{}"`) olarak eklenir.
6. **Dönem Sınırlarının Önceden Hesaplanması:** `period_start` ve `period_end` kolonları Gold'a ertelenmeden doğrudan Silver'da hesaplanır; böylece `align_service` resample işlemlerinde ek dönüşüm gerekmez.

---

## 2. Tablo Şemaları (Veri Modelleri)

Silver katmanı fiziksel olarak iki adet optimize Parquet dosyası üretir ve bu dosyalar DuckDB'ye bağlanır:

### Tablo 1: `silver_evds_observations`
* **Fiziksel Dosya:** `data/silver/evds/observations.parquet`
* **DuckDB Tablo/View:** `silver.evds_observations`
* **Rolü:** Zaman serisi gözlem olgularını (Fact Table) barındıran tekil uzun (Tall/Long) tablo.

| Kolon Adı | Veri Tipi | Zorunlu? | Örnek Değer | Açıklama ve Kural |
|---|---|---|---|---|
| **`series_id`** | `VARCHAR` | Evet | `'EVDS:TP.DK.USD.A.YTL'` | `<SOURCE>:<RAW_CODE>` formatında kanonik birincil seri anahtarı. |
| **`source`** | `VARCHAR` | Evet | `'EVDS'` | Veri sağlayıcı kaynak sistem. |
| **`date`** | `DATE` | Evet | `2021-01-04` | Standart ISO 8601 gözlem tarihi (`YYYY-MM-DD`). |
| **`period_start`** | `DATE` | Evet | `2021-01-01` | Gözlemin ait olduğu dönemin başlangıç tarihi (`YYYY-MM-DD`). |
| **`period_end`** | `DATE` | Evet | `2021-01-31` | Gözlemin ait olduğu dönemin bitiş tarihi (`YYYY-MM-DD`). |
| **`value`** | `DOUBLE` | Hayır | `7.4320` | Temizlenmiş sayısal değer. Eksik/tatil günlerinde `NULL`. |
| **`freq`** | `VARCHAR` | Evet | `'D'` | Kanonik frekans kodu (`D`, `W`, `M`, `Q`, `Y`). |
| **`dims`** | `VARCHAR` | Evet | `"{}"` | Boyut kırılımı JSON objesi. EVDS için her zaman `"{}"`. |

---

### Tablo 2: `silver_evds_series` (Metadata Dimension)
* **Fiziksel Dosya:** `data/silver/evds/series_metadata.parquet`
* **DuckDB Tablo/View:** `silver.evds_series`
* **Rolü:** Gözlem tablosunu hafif tutan, serilerin `metadata_raw.json` (TCMB resmi API) üzerinden gelen zengin tanımlarını içeren boyut tablosu (Dimension Table).
* **Sıfır-Manifest Bağımlılığı İlkesi:** Manifest sadece çekilecek serilerin kod listesidir. Boyut tablosundaki hiçbir metinsel kolon manifestten beslenmez; tüm veriler %100 resmi TCMB API metadatasından ve ham verinin kendisinden üretilir.

| Kolon Adı | Veri Tipi | Kaynak | Örnek Değer | Açıklama ve Kural |
|---|---|---|---|---|
| **`series_id`** | `VARCHAR` | Otomatik | `'EVDS:TP.DK.USD.A.YTL'` | Kanonik ID (Fact tablosuna JOIN anahtarı). |
| **`series_code`** | `VARCHAR` | `metadata_raw.json` | `'TP.DK.USD.A.YTL'` | Ham EVDS seri kodu (`SERIE_CODE`). |
| **`series_name`** | `VARCHAR` | `metadata_raw.json` | `'(USD) ABD Doları (Döviz Alış)'` | TCMB resmi katalog adı (`SERIE_NAME`, çift boşlukları temizlenmiş). |
| **`category`** | `VARCHAR` | `metadata_raw.json` | `'doviz_kurlari'` | Resmi `DATAGROUP_NAME` alanından otomatik türetilen standart slug. |
| **`tcmb_category`**| `VARCHAR` | `metadata_raw.json` | `'TCMB DÖVİZ KURLARI'` | Resmi TCMB üst kategori adı. |
| **`tcmb_datagroup`**| `VARCHAR`| `metadata_raw.json` | `'Döviz Kurları'` | Resmi TCMB veri grubu adı (`DATAGROUP_NAME`). |
| **`freq`** | `VARCHAR` | `metadata_raw.json` | `'D'` | **Tek Doğruluk Kaynağı:** TCMB resmi `FREQUENCY_STR` alanının (`GÜNLÜK` → `D`, `HAFTALIK(CUMA)` → `W`, `AYLIK` → `M`) kanonik koda dönüştürülmesiyle elde edilir. |
| **`unit`** | `VARCHAR` | `metadata_raw.json` | `'Türk lirası'` | TCMB'nin resmi ölçü birimi (`BIRIMI` alanı). |
| **`description`** | `VARCHAR` | `metadata_raw.json` | `'Bir önceki iş günü saat 15:30'da...'` | TCMB'nin resmi metodoloji ve tanım açıklaması (`NOTE` alanı). |
| **`tags`** | `VARCHAR[]` | `metadata_raw.json` | `["Kurlar", "Döviz", "Günlük"]` | TCMB'nin resmi arama etiketleri (`TAG` alanı ayrıştırılarak diziye çevrilir). |
| **`source`** | `VARCHAR` | Sabit | `'EVDS'` | Kaynak ('EVDS'). |

---

## 3. Veri Dönüştürme ve Temizleme Kuralları

### 3.1. Tarih ve Dönem Dönüşüm Matrisi

> 🔍 **Haftalık Gün Kontrolü ve Doğrulaması:** 2021–2026 arasındaki 7 haftalık serimizin (`TP.KTF10..17`, `HPBITABLO`, `TRY.MT02`) tamamındaki **284 gözlemin 284'ü de (%100) istisnasız CUMA günüdür** (kodla doğrulanmıştır).  
> ⚠️ **Haftalık Dönem Kuralı (ISO Hafta Standardı):** Raporlanan Cuma günü için o haftanın başlangıcı (`period_start`), Cuma'dan 4 gün önceki **Pazartesi** günüdür (`date - timedelta(days=date.weekday())`). Dönem bitişi (`period_end`) ise raporlanan **Cuma** günüdür (`date`). Böylece BDDK haftalık verileriyle hizalanırken (align_service) 1-2 günlük faz kayması ve korelasyon bozulması engellenir.

| Frekans | Gelen Ham Tarih Formatı | `date` | `period_start` | `period_end` | Hesaplama Yöntemi |
|---|---|---|---|---|---|
| **Günlük (`D`)** | `04-01-2021` (`DD-MM-YYYY`) | `2021-01-04` | `2021-01-04` | `2021-01-04` | `period_start = date`, `period_end = date` |
| **Haftalık (`W`)** | `08-01-2021` (Cuma günü) | `2021-01-08` | `2021-01-04` (Pazartesi) | `2021-01-08` (Cuma) | `period_start = date - timedelta(days=date.weekday())`, `period_end = date` |
| **Aylık (`M`)** | `2021-1` veya `2021-01` (`YYYY-M`) | `2021-01-01` | `2021-01-01` (Ayın 1. günü) | `2021-01-31` (Ayın son günü) | `period_start = date.replace(day=1)`, `period_end = date + MonthEnd(0)` |
| **Çeyreklik (`Q`)**| `2021-Q1` | `2021-01-01` | `2021-01-01` (Çeyrek 1. günü) | `2021-03-31` (Çeyrek son günü) | Çeyrek başlangıç ve bitiş sınırları |

### 3.2. Değer (`value`) Temizleme Kuralları
1. **Tip:** Tüm değerler IEEE 754 64-bit float (`DOUBLE`) tipine dönüştürülmelidir.
2. **Virgül/Nokta Ayrımı:** Değer metinlerinde virgül varsa noktaya çevrilir (`"26,76"` → `26.76`).
3. **Null Yönetimi:** `None`, `null`, `""` (boş string), `"-"`, `"ND"` gibi eksik gözlem ifadeleri doğrudan `NULL` (`np.nan`) yapılır.
4. **Hafta Sonu & Tatiller:** EVDS'in yayımlamadığı tatil günleri Silver katmanında satır uydurularak çoğaltılmaz (as-is gözlem korunur). İleriye dönük tamamlama (forward-fill) ihtiyacı analiz anında (Gold veya View) karşılanır.

### 3.3. Kanonik Frekans Eşleme Tablosu (`metadata_raw.json` -> `freq`)
Frekans, karmaşık tahminler veya regex yerine doğrudan TCMB resmi metadatasındaki `FREQUENCY_STR` alanından eşlenir:

| TCMB Resmi `FREQUENCY_STR` | Kanonik Kod | Açıklama |
|---|---|---|
| `"GÜNLÜK"` | **`D`** | Günlük seriler |
| `"HAFTALIK(CUMA)"` veya `"HAFTALIK"` | **`W`** | Haftalık seriler (Pazartesi-Cuma periyodu) |
| `"AYLIK"` | **`M`** | Aylık seriler (Ay başı - Ay sonu periyodu) |
| `"3 AYLIK"` veya `"ÇEYREKLİK"` | **`Q`** | Çeyreklik seriler |
| `"YILLIK"` | **`Y`** | Yıllık seriler |

* **Senkron Güvencesi:** `metadata_raw.json`'dan çözümlenen kanonik frekans kodu (`D`, `W`, `M`), hem `observations.parquet` satırlarına hem de `series_metadata.parquet` kaydına ortak tek değer olarak yazılır; iki tablo arasında sıfır uyumsuzluk garantilenir.

### 3.4. Metadata ve Katalog Bütünlük Doğrulama Testleri (Testing Strategy)
Geliştirilecek birim testlerinde (`backend/tests/modules/evds/test_transformer.py`) aşağıdaki veri doğrulamaları %100 kontrol edilir:
1. **Katalog Varlık Kontrolü:** Manifestte yer alan her `code`'un `evds_catalog.parquet` ve `metadata_raw.json` içinde tam olarak 1 resmi kaydı bulunmalıdır.
2. **Zorunlu Metadata Bütünlüğü:** `metadata_raw.json` içindeki serilerin `SERIE_NAME`, `DATAGROUP_NAME`, `BIRIMI` ve `NOTE` alanları boş veya `None` olamaz.
3. **Frekans Örtüşme Kontrolü:** Veriden tespit edilen kanonik frekans (`detected_freq`), TCMB'nin resmi `FREQUENCY_STR` metniyle (örn. `W` ile `HAFTALIK(CUMA)`) uyumlu olmalıdır.
4. **Çapraz Tablo Referans Tutarlılığı:** `observations.parquet` içindeki `series_id` kümesi ile `series_metadata.parquet` içindeki `series_id` kümesi birbirine tam eşit (`set(obs) == set(meta)`) ve her serinin her iki tablodaki `freq` değeri istisnasız aynı olmalıdır.

---

## 4. İki Aşamalı Silver Boru Hattı Mimarisi (Pipeline Architecture)

Silver katmanı, **Ağ Erişimi (Metadata Fetching)** ile **Veri Dönüşümünü (Offline Transforming)** birbirinden kesin olarak ayırır. Böylece dönüşüm adımı tamamen deterministik, offline ve tekrarlanabilir (idempotent) kalır.

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│ AŞAMA 1: backend/app/modules/evds/metadata.py (Ağ / API Entegrasyonu)                  │
│                                                                                        │
│ 1. series_manifest.yaml'ı oku (seri kodları ve datagroup listesi)                      │
│ 2. data/bronze/evds/metadata_raw.json var mı kontrol et                                │
│    ├── Varsa: İçindeki mevcut serileri tespit et, atla ([SKIP])                         │
│    └── Yoksa veya eksik seriler varsa:                                                 │
│        └── Sadece eksik serilerin veri grupları için TCMB API'ye sor (raw=True)        │
│ 3. Yeni çekilen zengin metadataları metadata_raw.json'a birleştirip kaydet (upsert)   │
└───────────────────────────────────────────┬────────────────────────────────────────────┘
                                            │ (Yerel JSON dosyaları hazır)
                                            ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│ AŞAMA 2: backend/app/modules/evds/transformer.py (Tamamen Offline & Hızlı)             │
│                                                                                        │
│ 1. data/bronze/evds/*.json (Ham gözlemler) ve metadata_raw.json'ı oku                  │
│ 2. NOTE, BIRIMI, TAG, SERIE_NAME gibi zengin verileri metadata_raw.json'dan al         │
│ 3. Değerleri temizle (DOUBLE), tarihleri ISO yap, Pazartesi-Cuma periyotlarını hesapla │
│ 4. İki adet Parquet dosyası üret (Atomik yazma):                                       │
│    ├── data/silver/evds/observations.parquet    (Fact - gözlemler)                     │
│    └── data/silver/evds/series_metadata.parquet (Dimension - zengin katalog)          │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

### 4.1. `metadata.py` Çalışma Mantığı ve `metadata_raw.json`
* **Dosya:** `data/bronze/evds/metadata_raw.json`
* **Amaç:** 53.710 serilik tüm EVDS kataloğunu her seferinde baştan taramak yerine, yalnızca manifestte yer alan serilerin TCMB resmi metodoloji ve metadata kayıtlarını tutmaktır.
* **İdempotentlik:**
  - `metadata.py` çalıştığında önce diskteki `metadata_raw.json`'ı inceler.
  - Manifestteki tüm seriler zaten `metadata_raw.json` içinde mevcutsa **hiçbir ağ/API sorgusu atmaz** (`[SKIP] All metadata up-to-date`).
  - Manifeste yeni bir seri eklendiğinde (örn. 23. seri), yalnızca bu yeni serinin `metadata_raw.json`'da olmadığını görür; sadece ilgili veri grubunu API'den çeker ve JSON dosyasına ekler.
* **Depolanan Zengin Alanlar (TCMB API `raw=True` Çıktısı):**
  - `SERIE_CODE`: Orijinal kod (`TP.DK.USD.A.YTL`)
  - `SERIE_NAME`: TCMB resmi katalog adı
  - `DATAGROUP_CODE` / `DATAGROUP_NAME`: Resmi veri grubu
  - `FREQUENCY_STR`: Resmi frekans (`HAFTALIK(CUMA)`, `AYLIK`, vb.)
  - `DEFAULT_AGG_METHOD_STR`: Resmi toplulaştırma yöntemi
  - `START_DATE` / `END_DATE`: Serinin veri başlangıç ve bitiş tarihleri
  - `BIRIMI`: TCMB resmi ölçü birimi (TL, Yüzde, ABD Doları, vb.)
  - `NOTE`: TCMB resmi metodoloji ve tanım açıklaması (LLM ve kullanıcılar için kritik)
  - `TAG`: Arama ve filtreleme etiketleri (`Kurlar, Döviz, Günlük`)

---

## 5. Dosya ve Dizin Yerleşimi

```
c:\Projects\kkb\
├── data/
│   ├── bronze/evds/                    # Girdi: Ham JSON'lar & metadata
│   │   ├── evds_catalog.parquet        # Keşif kataloğu
│   │   ├── metadata_raw.json           # YENİ: Manifestteki serilerin zengin TCMB metadatası
│   │   ├── TP.DK.USD.A.YTL.json        # Ham gözlem JSON'ları (22 seri)
│   │   └── ...
│   └── silver/evds/                    # Çıktı: F-003 tarafından üretilecek Parquet dosyaları
│       ├── observations.parquet        # Fact tablosu (tüm serilerin normalize gözlemleri)
│       └── series_metadata.parquet     # Dimension tablosu (metadata_raw.json + manifest)
│
├── backend/
│   ├── app/modules/evds/               # EVDS modülü (Bronze ve Silver mantığı burada toplanır)
│   │   ├── __init__.py
│   │   ├── client.py                   # EVDS API istemcisi (raw=True destekli)
│   │   ├── catalog.py                  # Keşif mantığı
│   │   ├── catalog_store.py            # Ortak Parquet erişimi
│   │   ├── ingestion.py                # Bronze gözlem indirme
│   │   ├── metadata.py                 # YENİ: Manifest serilerinin TCMB metadatasını çeken/yöneten modül
│   │   ├── series_manifest.yaml        # Seri yönergesi
│   │   └── transformer.py              # YENİ: Silver dönüşüm motoru (Bronze JSON + metadata -> Parquet)
│   ├── scripts/
│   │   ├── bddk/
│   │   └── edvs/
│   │       ├── seed_catalog.py         # Keşif CLI
│   │       ├── seed_evds.py            # Bronze indirme CLI
│   │       └── seed_silver_evds.py     # YENİ: Silver boru hattı CLI (metadata + transformer)
│   └── tests/modules/evds/             # EVDS testleri
│       ├── conftest.py
│       ├── test_catalog.py
│       ├── test_client.py
│       ├── test_ingestion.py
│       ├── test_metadata.py            # YENİ: metadata.py birim ve idempotency testleri
│       └── test_transformer.py         # YENİ: Silver şema, tip, tarih, senkron testleri
│
└── docs/handoff/F-003/
    └── kurallar.md                     # BU DOSYA (Bağlayıcı mimari ve şema kuralları)
```

---

## 6. İdempotency ve Atomik Yazma Güvencesi

1. **Atomik Yazma:** Parquet dosyaları (`observations.parquet`, `series_metadata.parquet`) ve JSON dosyaları (`metadata_raw.json`) yazılırken önce aynı dizinde `.tmp_{pid}_{uuid}` geçici dosyasına yazılır ve `Path.replace()` (`os.replace`) ile atomik olarak asıl dosyanın üzerine taşınır.
2. **Hata İzolasyonu:** Serilerden birinde veri bozulması veya JSON parse hatası meydana gelirse tüm işlem çökmez; hata loglanır, `failed_series` listesine eklenir ve işlem sonunda özet raporlanır.
3. **Deterministik Sıralama:** Çıktı `observations.parquet` dosyası her zaman `(series_id ASC, date ASC)` sıralı olarak kaydedilir; böylece zaman serisi filtrelemelerinde diskten okuma performansı maksimize edilir.

---

## 7. Yeni Seri Ekleme ve Güncelleme Stratejisi (End-to-End İş Akışı)

İlerleyen aşamalarda manifestoya 23. veya 50. bir seri eklendiğinde sistemin baştan sona nasıl çalışacağı adım adım tanımlanmıştır:

1. **Adım 1: Manifest Güncelleme:**
   - `series_manifest.yaml` dosyasına yeni seri tanımı eklenir.
2. **Adım 2: Bronze Gözlem Çekimi:**
   - `python backend/scripts/seed_evds.py` çalıştırılır.
   - Mevcut 22 seri diskte olduğu için `[SKIP]` edilir, sadece yeni serinin Bronze gözlem JSON'ı indirilir.
3. **Adım 3: Silver Boru Hattı Çalıştırma (`backend/scripts/edvs/seed_silver_evds.py`):**
   - **Alt Adım 3.1 (`metadata.py`):** `metadata_raw.json` dosyasını kontrol eder. 22 seri zaten olduğu için onları atlar; sadece yeni serinin ait olduğu veri grubunu TCMB API'den çeker ve `metadata_raw.json`'a ekler.
   - **Alt Adım 3.2 (`transformer.py`):** 
     - Akıllı modda: Yeni seriyi ve güncellenen JSON'ları parse eder, mevcut `observations.parquet` ve `series_metadata.parquet` dosyalarına atomik olarak enjekte eder (`upsert`).
     - Ya da istenirse `--full-refresh` bayrağı ile tüm yerel JSON'lardan iki Parquet dosyasını sıfırdan 0.2 saniyede derler.


