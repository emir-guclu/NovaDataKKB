# Design Note (Dev) — F-001

Status: complete

## Data model
- Entity: EVDS Raw Data & Catalog (`db-schema.md`'de karşılığı yok - Bu feature veritabanı şemasına dokunmayıp verileri Bronze katmanına salt JSON ve Parquet olarak kaydeder)
  - `data/bronze/evds/evds_catalog.parquet`: Tüm kategorileri, alt kategorileri ve seri metadatalarını içeren ham/değiştirilemez metadata kataloğu. `is_ingested`, `fetch_status`, `last_ingested_at` alanlarını da barındırır.
  - `data/bronze/evds/{seri_kodu}.json`: raw JSON — UTF-8

## API contract
- Sistem dışarıya bir API sunmuyor, dış API'yi tüketiyor.
- `GET EVDS API`
  - Request: `evds.get_data(code, startdate, enddate, raw=True)` ve katalog için `get_main_categories()`, `get_sub_categories()`, `get_series()`
  - Response: Raw JSON payload
  - Errors: `HTTP 429` (Rate Limit) -> `EVDS_API_KEY_1..4` anahtarları arasında rotasyon tetikler.

## Components
- `evds/client.py` (Service): EVDS API (pip) paketini sarmalamak, `.env` anahtarlarını okumak ve API anahtarı rotasyonunu yönetmek.
- `evds/catalog.py` (Business Logic - Discovery): `get_main_categories` -> `get_sub_categories` -> `get_series` zinciriyle EVDS API'yi tarayıp tüm kataloğu çıkarır ve `catalog_store.py` üzerinden kaydeder.
- `evds/catalog_store.py` (Data Access): `data/bronze/evds/evds_catalog.parquet` dosyasına erişim. Race condition'ları önlemek için ortak okuma, yazma ve upsert işlemlerini kapsüller.
- `evds/ingestion.py` (Business Logic - Ingestion): `series_manifest.yaml` dosyasını ayrıştırmak, idempotent indirme mantığını yürütmek, API'den ham veriyi JSON olarak kaydetmek ve ardından `catalog_store.py` üzerinden katalogda ilgili serinin indirme durumunu (`is_ingested`, `fetch_status`, `last_ingested_at`) güncellemek.
- `scripts/seed_catalog.py` (CLI Trigger): Keşif mantığını (`catalog.py`) çağıran ana tetikleyici betik.
- `scripts/seed_evds.py` (CLI Trigger): İndirme mantığını (`ingestion.py`) çağıran hızlı tetikleyici betik.
- `evds/series_manifest.yaml` (Configuration): Çekilecek serilerin tanımlandığı bildirime dayalı yapılandırma dosyası.

## Business rule mapping
- BR-01 → `evds/client.py`
- BR-02 → `evds/ingestion.py` & `evds/series_manifest.yaml`
- BR-03 → `evds/ingestion.py` (`raw=True`)
- BR-04 → `evds/ingestion.py` (idempotency, dosya boyutu kontrolü)
- BR-05 → `evds/client.py` (Key rotasyonu)
- BR-06 → `evds/catalog.py` (Keşif), `evds/ingestion.py` (İndirme), `scripts/seed_catalog.py`, `scripts/seed_evds.py` (Sorumluluk ayrımı)
- BR-07 → `evds/catalog_store.py` (Parquet ortak erişimi)
- BR-08 → `evds/series_manifest.yaml` (Tarih aralığı: `01-01-2021` - `01-06-2026`)
- BR-09 → `evds/series_manifest.yaml` (22 öncelikli makro seri: Konut, Ticari, Tüketici kredileri, TÜFE, ÜFE, KFE, Döviz, Fonlama faizi, Reel sektör, vb.)
- BR-10 → `tests/modules/evds/` (Catalog, Client ve Ingestion birim testleri)
- BR-11 → `evds/client.py` (EVDS 1000 kayıt tavanı durumunda otomatik geriye dönük pagination / date windowing)
- BR-12 → `evds/ingestion.py` (None yanıt tespiti, `failed_count` sayacı ve katalogda `fetch_status='FAILED'` işaretleme)

## Task breakdown (Development)
- T1: Yönerge Dosyası ve İstemci Hazırlığı — servis ettiği: `Scenario 1`, `Scenario 4` — dosyalar: `backend/app/modules/evds/series_manifest.yaml`, `backend/app/modules/evds/client.py`
  - `series_manifest.yaml` dosyasını 22 doğrulanmış seri ve gerekli kolonlarla oluştur.
  - Rate limit durumunda anahtar rotasyonu yapabilen temel `EvdsClient` sınıfını geliştir.
- T2: Katalog Depolama Altyapısı (Store) — servis ettiği: `Scenario 5`, `Scenario 6` — dosyalar: `backend/app/modules/evds/catalog_store.py`
  - Parquet dosyası (`evds_catalog.parquet`) üzerinde thread-safe okuma, tümden yazma ve satır bazlı upsert işlemlerini yönetecek metotları geliştir.
- T3: Keşif Mantığı ve Betiği (Discovery) — servis ettiği: `Scenario 5` — dosyalar: `backend/app/modules/evds/catalog.py`, `backend/scripts/seed_catalog.py`
  - API'den kategori ve seri listelerini çekip `evds_catalog.parquet` olarak kaydeden mantığı ve CLI betiğini yaz.
- T4: Ingestion Logic (Veri Çekme ve Katalog Güncelleme) — servis ettiği: `Scenario 1`, `Scenario 2`, `Scenario 4`, `Scenario 6`, `Scenario 8` — dosyalar: `backend/app/modules/evds/ingestion.py`, `backend/scripts/seed_evds.py`
  - İndirme (idempotency) mekanizmasını kur. `raw=True` ile JSON kaydet.
  - İndirme sonrası `catalog_store.py` üzerinden ilgili serinin durumunu güncelle (`is_ingested=True`).
  - Hata durumunda (`None` dönen seriler) `failed_count` artır ve katalogda `fetch_status='FAILED'` olarak işaretle.
- T5: Otomatik Geriye Dönük Sayfalama (Pagination) — servis ettiği: `Scenario 7` — dosyalar: `backend/app/modules/evds/client.py`
  - EVDS 1000 kayıt limitine ulaşıldığında (`len(res) == 1000`), ilk kaydın tarihinden geriye doğru eksik zaman dilimini otomatik olarak ardışık ek isteklerle çek.
  - Alınan parçaları tarihe göre tekilleştir (deduplicate) ve kronolojik sırada birleştirerek çağıran koda şeffaf biçimde döndür.

## Coverage check
- Scenario 1 (Happy Path - Indirme) → T1, T4 ✓
- Scenario 2 (Idempotency - Atlama) → T4 ✓
- Scenario 3 (Key Rotation) → T1 ✓
- Scenario 4 (Manifest Format Error) → T4 ✓
- Scenario 5 (Keşif - Katalog Oluşturma) → T2, T3 ✓
- Scenario 6 (Katalog Güncelleme) → T2, T4 ✓
- Scenario 7 (1000 Kayıt Sınırında Geriye Dönük Sayfalama) → T5 ✓
- Scenario 8 (Hata Yönetimi ve FAILED Durumu) → T4 ✓

## Open questions (varsa)
- Bulunmuyor.

