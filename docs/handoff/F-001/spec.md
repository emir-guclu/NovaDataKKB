# Spec: F-001 — EVDS Veri Temini (Bronze Katmanı)

## 1. Spec Durumu
**Verified & Completed** (Doğrulandı ve Tamamlandı)

---

## 2. Amaç ve Başarı Sinyali
Analitik ajan ve görselleştirme motorları ihtiyaç duydukları TCMB makroekonomik serilerine güvenilir ve tekrarlanabilir bir kaynaktan erişebilsin diye; sistem, belirlenen serileri EVDS API üzerinden çekmeli ve kaynaktan geldiği ham haliyle (Bronze Layer) yerel dosya sistemine arşivlemelidir.

**Başarı Kriteri:**
`backend/scripts/seed_evds.py` komutu çalıştırıldığında, `series_manifest.yaml` dosyasında tanımlanan tüm serilerin `data/bronze/evds/{seri_kodu}.json` formatında başarıyla kaydedilmesi ve ikinci kez çalıştırıldığında mevcut dosyaları tekrar indirmeden (skip) hızlıca tamamlanmasıdır.

---

## 3. Kapsam / Kapsam Dışı

**Kapsam İçi:**
- `evds` pip paketi (v0.4.0) ve `.env` anahtar havuzunu (`EVDS_API_KEY_1..4`) kullanan servis sarmalayıcısı.
- Bildirime dayalı seri yönergesi (`backend/app/modules/evds/series_manifest.yaml`) tanımlanması ve okunması.
- Keşif (Discovery) Katmanı: Tüm EVDS kategorilerini ve serilerini tarayıp `data/bronze/evds/evds_catalog.parquet` dosyasına yazacak `catalog.py` modülü ve tetikleyicisi `seed_catalog.py`.
- İdempotent (akıllı) indirme mantığı: Bronze klasöründe ilgili serinin geçerli JSON dosyası varsa atlama (skip), yoksa API'den çekme.
- Katalog Güncelleme: `ingestion.py` tarafından seri çekildiğinde `data/bronze/evds/evds_catalog.parquet` dosyasındaki `is_ingested`, `fetch_status`, `last_ingested_at` alanlarının güncellenmesi.
- Ortak Veri Depolama: Parquet okuma/yazma/upsert işlemlerinin race condition'ları önlemek için `catalog_store.py` modülünde toplanması.
- Ham verilerin `raw=True` parametresiyle hiçbir veri/tip kaybı olmadan JSON olarak `data/bronze/evds/{seri_kodu}.json` altına yazılması.
- Çekirdek iş mantığının `backend/app/modules/evds/`, tek seferlik tetikleyici betiklerin (`seed_catalog.py` ve `seed_evds.py`) `backend/scripts/` altında konumlandırılması.
- Çekilecek seriler için varsayılan tarih aralığı: `01-01-2021` – `01-06-2026`.

**Kapsam Dışı:**
- ❌ **Silver ve Gold Katmanları:** Verilerin Parquet'ye dönüştürülmesi, float/tarih tip temizliği, eksik günlerin tamamlanması veya `lakehouse.duckdb` içine aktarımı.
- ❌ **LLM & Agent Tools:** Modelin doğrudan çağıracağı araçlar (`search_series`, `run_sql` vb.).
- ❌ **Analitik Hesaplamalar:** TÜFE ile enflasyondan arındırma, korelasyon veya grafik çizimleri.

---

## 4. Kullanıcı Hikayesi (User Story)
**Veri Mühendisi ve Sistem Yöneticisi olarak;**  
TCMB EVDS serilerini tüm kategorileriyle keşfedebilmek (catalog), bu kataloğu saklayabilmek ve sadece öncelikli serileri tek bir yönerge dosyasından yöneterek hızlıca Bronze katmanına indirebilmek (ingestion) istiyorum,  
**Böylelikle;**  
Sistemin ihtiyaç duyduğu ham finansal veriler güvenli, idareli (kotayı koruyan) ve tutarlı bir göl arşivinde hazır olsun, ayrıca geniş keşif işlemi ile dar indirme işlemi birbirine karışmasın.

---

## 5. Numaralandırılmış İş Kuralları (Business Rules)

* **BR-01:** EVDS API erişimi için `evds` pip paketi kullanılmalı ve `app/modules/evds/client.py` altında sarmalanmalıdır. *(Kaynak: ADR-0002, T-08)*
* **BR-02:** Çekilecek tüm seriler `backend/app/modules/evds/series_manifest.yaml` yönerge dosyasında tanımlanmalıdır. Dosyada her seri için `code`, `name`, `category`, `frequency`, `start_date` ve `end_date` alanları yer almalıdır.
* **BR-03:** Ingestion işlemi sırasında `evds.get_data(...)` çağrıları mutlaka `raw=True` parametresi ile yapılmalı, TCMB'den dönen saf JSON çıktısı bozulmadan `data/bronze/evds/{seri_kodu}.json` yoluna UTF-8 olarak kaydedilmelidir. *(Kaynak: ADR-0002)*
* **BR-04 (Idempotency):** Seri çekim döngüsü başlamadan önce hedef dosya (`data/bronze/evds/{code}.json`) diskte mevcut mu ve dosya boyutu > 0 bayt mı kontrol edilmelidir. Dosya varsa API çağrısı yapılmamalı, `[SKIP]` logu basılarak sonraki seriye geçilmelidir.
* **BR-05 (Key Rotation):** API çağrılarında `.env` içindeki `EVDS_API_KEY_1`, `EVDS_API_KEY_2`, `EVDS_API_KEY_3`, `EVDS_API_KEY_4` anahtar havuzu kullanılmalıdır. Bir anahtar HTTP 429 (Rate Limit) veya kimlik hatası alırsa, istemci otomatik olarak sıradaki anahtara geçmeli ve isteği tekrarlamalıdır. *(Kaynak: T-43, ADR-0002)*
* **BR-06 (Kod Ayrımı - Keşif ve İndirme):** Sistem iki ayrı sorumluluğa ayrılmalıdır:
  - Keşif (Discovery): `backend/app/modules/evds/catalog.py` modülü `get_main_categories` -> `get_sub_categories` -> `get_series` zinciriyle tüm kataloğu tarayıp `data/bronze/evds/evds_catalog.parquet` dosyasına yazmalıdır. Bu uzun süren işlem `backend/scripts/seed_catalog.py` ile tetiklenmelidir.
  - İndirme (Ingestion): `backend/app/modules/evds/ingestion.py` modülü, sadece `series_manifest.yaml` dosyasındaki öncelikli serileri işlemeli ve indirmelidir. Bu hızlı işlem `backend/scripts/seed_evds.py` ile tetiklenmelidir.
* **BR-07 (Ortak Katalog Erişimi):** Hem `catalog.py` (keşif/yeni satır ekleme) hem de `ingestion.py` (indirme durumunu, `is_ingested`, güncellenme) aynı parquet dosyasına erişeceği için tüm okuma/yazma/upsert işlemleri `backend/app/modules/evds/catalog_store.py` modülünde toplanmalıdır. Bu, race condition ve şema tutarsızlıklarını engeller.
* **BR-08 (Tarih Aralığı):** Çekilecek makro serilerin varsayılan tarih filtreleri hackathon brifingi doğrultusunda `01-01-2021` ile `01-06-2026` aralığı olmalıdır.
* **BR-09 (Seri Kapsamı):** İlk aşamada 4 çekirdek seri ile başlanmış, ardından 53.710 satırlık resmi EVDS kataloğundan doğrulanarak kredi faizleri, kredi hacimleri, enflasyon (TÜFE/ÜFE), döviz kurları, TCMB politika/fonlama faizleri, reel sektör ve rezerv göstergelerini kapsayan **22 öncelikli seriye** genişletilmiştir.
* **BR-10 (Test Kapsamı):** `tests/modules/evds/test_catalog.py`, `test_client.py` ve `test_ingestion.py` dosyaları oluşturulmalı, discover_all, anahtar rotasyonu, sayfalama ve `is_ingested` idempotency kuralları birim testlerle (%100 yeşil) doğrulanmalıdır.
* **BR-11 (Otomatik Geriye Dönük Sayfalama / 1000 Kayıt Sınırı):** EVDS REST API günlük serilerde tek çağrıda en fazla 1000 kayıt döndürür ve eski tarihleri keser. İstemci (`client.py`), gelen ham yanıtta `len(res) == 1000` tespit ettiğinde ilk kaydın tarihinden geriye doğru eksik kalan zaman dilimini otomatik olarak ardışık ek sorgularla çekmeli, kronolojik sırada birleştirmeli ve tarihe göre tekilleştirmelidir (deduplication). Böylece 2021-2026 aralığı eksiksiz (örn. kurlar için ~1978 gün) tamamlanmalıdır.
* **BR-12 (Katı Doğrulama ve Hata Raporlama):** API çağrısı `None` dönerse, seri tipi hatalıysa veya JSON ayrıştırılamazsa indirme sessizce başarılı sayılmamalı; `failed_count` artırılmalı ve katalogdaki seri durumu `fetch_status="FAILED"`, `is_ingested=False` olarak kaydedilmelidir.
---

## 6. Dosya ve Klasör Düzeni
```
data/
└── bronze/
    └── evds/
        ├── evds_catalog.parquet         # Ham/değiştirilemez metadata kataloğu
        ├── TP.KTF10.json
        ├── TP.FG.J0.json
        ├── TP.HKFE01.json
        └── TP.DK.USD.A.YTL.json

backend/
├── app/
│   └── modules/
│       └── evds/
│           ├── __init__.py
│           ├── client.py            # EVDS API istemcisi (httpx wrapper)
│           ├── catalog.py           # YENİ - discover_all mantığı (kataloğu tarayıp günceller)
│           ├── ingestion.py         # Mevcut - manifest'teki serileri çekip bronze'a yazar
│           ├── catalog_store.py     # YENİ - parquet okuma/yazma/upsert ortak işlemleri
│           └── series_manifest.yaml # Çekilecek öncelikli seriler listesi
│
├── scripts/
│   ├── seed_catalog.py              # YENİ - catalog.py'yi çağırır (tam tarama, uzun sürer)
│   └── seed_evds.py                 # Mevcut - ingestion.py'yi çağırır (hızlı, öncelikli seriler)
│
└── tests/
    └── modules/
        └── evds/
            ├── conftest.py
            ├── test_client.py
            ├── test_ingestion...
            └── test_catalog.py      # YENİ - discover_all mantığı ve idempotency testi
```

---

## 7. Açık Sorular ve İleriye Dönük İyileştirmeler
* `[FUTURE]` İlerleyen aşamalarda bu `series_manifest.yaml` dosyası Admin Dashboard ekranına bağlanarak arayüz üzerinden dinamik seri ekleme/güncelleme imkanı sağlanabilir.
* `[FUTURE]` Yönergedeki seriler `F-002` aşamasında DuckDB `catalog.metadata` şemasına otomatik aktarılacaktır.
