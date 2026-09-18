# NovaDataKKB Veri Pipeline Kurulum ve Çalıştırma Rehberi

Bu doküman, NovaDataKKB projesinde Bronze verilerden başlayarak Silver, Canonical Silver ve Monthly Aligned katmanlarının hangi sırayla oluşturulacağını açıklar.

Gold katmanı bu akışın devamında yer alacaktır ancak şu an bu dokümanın kapsamı dışındadır.

---

# 1. Ortam Hazırlığı

Tüm komutlar repository kök dizininden çalıştırılmalıdır.

Virtual environment yoksa oluştur:

    python3 -m venv .venv

Aktifleştir:

    source .venv/bin/activate

Python'ın virtual environment üzerinden geldiğini kontrol et:

    which python
    python --version

Backend importlarının doğru çalışması için proje komutlarında `PYTHONPATH` tanımlanmalıdır:

    # Linux / macOS (Bash):
    PYTHONPATH=backend python -m pytest

    # Windows (PowerShell):
    $env:PYTHONPATH="backend"; python -m pytest

    # Windows (CMD):
    set PYTHONPATH=backend && python -m pytest

---

# 2. Bronze Veri Yapısı

Silver katmanı oluşturulmadan önce kaynak verilerin aşağıdaki klasörlerde bulunması gerekir:

    data/
    └── bronze/
        ├── bddk/
        │   ├── weekly/
        │   ├── monthly/
        │   └── finturk/
        └── evds/

Şu anda kullanılan temel BDDK Bronze dosyaları:

    data/bronze/bddk/weekly/bddk_weekly_all_2021_2026.csv
    data/bronze/bddk/monthly/bddk_monthly_all_2021_2026_precise.csv
    data/bronze/bddk/finturk/bddk_finturk_all_2021_2026.csv

EVDS Bronze JSON dosyaları şu klasör altında bulunmalıdır:

    data/bronze/evds/

Bronze katmanını sıfırdan indirmek veya doğrulamak için tek komutlu orkestratörler:

    # BDDK Bronze verilerini doğrula/indir:
    PYTHONPATH=backend python backend/scripts/bddk/build_bronze_bddk.py

    # EVDS Bronze verilerini doğrula/indir:
    PYTHONPATH=backend python backend/scripts/evds/build_bronze_evds.py

---

# 3. BDDK Silver Katmanını Oluşturma

BDDK Bronze verilerinden normalize edilmiş Silver veriyi oluşturmak için:

    PYTHONPATH=backend python \
      backend/scripts/bddk/build_silver_bddk.py

Beklenen temel çıktılar:

    data/silver/bddk/observations.parquet
    data/silver/bddk/series_metadata.parquet

BDDK Silver katmanında doğal frekanslar korunur:

    Weekly  -> W
    Monthly -> M
    FinTürk -> Q

Kümülatif BDDK serilerinde raw veri korunur.

İncelenmiş YTD serileri için gerekli durumlarda ayrıca periodic türev serileri oluşturulur.

---

# 4. BDDK DuckDB Oluşturma

BDDK Silver verisini ayrıca source-specific DuckDB içerisine almak için:

    PYTHONPATH=backend python \
      backend/scripts/bddk/build_silver_duckdb.py

Çıktı:

    data/silver/bddk/bddk_silver.duckdb

Bu veritabanı BDDK tarafının ayrı olarak incelenmesi için kullanılabilir.

Cross-source ana Silver veritabanı değildir.

Ana ortak veritabanı ilerleyen aşamada oluşturulan:

    data/silver/silver.duckdb

dosyasıdır.

---

# 5. EVDS Silver Katmanını Oluşturma

EVDS Bronze verilerinden Silver katmanı oluşturmak için:

    PYTHONPATH=backend python \
      backend/scripts/evds/build_silver_evds.py \
      --full-refresh

Beklenen çıktılar:

    data/silver/evds/observations.parquet
    data/silver/evds/series_metadata.parquet

Bu script aynı zamanda manifest içinde beklenen EVDS serileri ile mevcut Bronze dosyalarını karşılaştırır.

Eksik Bronze seriler sessizce mevcut kabul edilmez.

Coverage bilgisi terminal çıktısında gösterilir.

---

# 6. Canonical Silver Katmanını Oluşturma

BDDK ve EVDS source-specific Silver katmanları hazırlandıktan sonra ortak Canonical Silver katmanı oluşturulur.

Çalıştır:

    PYTHONPATH=backend python \
      backend/scripts/build_silver_canonical.py

Ana çıktı:

    data/silver/silver.duckdb

Canonical Silver veritabanında iki ana tablo bulunur:

    observations
    series_metadata

Canonical Silver katmanının amacı BDDK ve EVDS verilerini ortak bir veri sözleşmesi altında birleştirmektir.

Temel kurallar:

    date = period_end

    ortak observation şeması

    ortak metadata şeması

    dims alanı native JSON

    FinTürk coğrafi alanları normalize edilir

    observation key:
    (series_id, date, dims)

    metadata ve observation arasında coverage kontrolü yapılır

Doğrulanmış mevcut build sonucu:

    451,700 observation
    963 seri
    0 duplicate observation key
    0 metadata'sız observation
    0 orphan metadata

---

# 7. Alignment Katmanı

Canonical Silver katmanındaki tüm seriler aynı frekansta değildir.

Örneğin:

    EVDS         -> D / W / M
    BDDK Weekly  -> W
    BDDK Monthly -> M
    FinTürk      -> Q

Gold katmanında bu verilerin birlikte analiz edilebilmesi için ortak bir zaman eksenine hizalanmaları gerekir.

Alignment işlemini yapan reusable servisler:

    backend/app/services/align_service.py
    backend/app/services/alignment_policies.py

Alignment katmanının batch builder scripti:

    backend/scripts/build_aligned_monthly.py

Çalıştır:

    PYTHONPATH=backend python \
      backend/scripts/build_aligned_monthly.py

Beklenen çıktılar:

    data/aligned/monthly/
    ├── observations.parquet
    ├── series_metadata.parquet
    └── aligned.duckdb

Alignment işlemi körlemesine resample yapmaz.

Her seri kendi ekonomik/veri semantiğine uygun policy ile dönüştürülür.

Şu anda kullanılan doğrulanmış politikalar:

    BDDK Weekly snapshot/balance serileri
    -> monthly last

    EVDS günlük döviz kuru serileri
    -> monthly mean

    EVDS haftalık faiz oranları
    -> monthly mean

    EVDS günlük TCMB fonlama göstergeleri
    -> monthly mean

    Monthly seriler
    -> olduğu gibi korunur

    Quarterly seriler
    -> quarter-end sparse

    Raw cumulative / YTD seriler
    -> aligned katmana alınmaz

Quarterly veriler varsayılan olarak aylara forward-fill edilmez.

Bu sayede olmayan aylık veri yapay olarak üretilmez.

Doğrulanmış mevcut alignment sonucu:

    311,678 observation
    917 seri
    212 explicit D/W alignment policy
    0 duplicate key
    0 imputed row

---

# 8. Canonical Silver Testleri

Canonical Silver ve BDDK regression testlerini çalıştırmak için:

    PYTHONPATH=backend python -m pytest \
      backend/tests/test_silver_canonical.py \
      backend/tests/test_silver_canonical_duckdb.py \
      backend/tests/modules/bddk \
      -v

Tüm süit: `pytest` → 319 test (314 geçer, 5 atlanır).

---

# 9. Alignment Testleri

Alignment servislerini ve gerçek aligned DuckDB çıktısını test etmek için:

    PYTHONPATH=backend python -m pytest \
      backend/tests/services/test_align_service.py \
      backend/tests/services/test_alignment_policies.py \
      backend/tests/services/test_aligned_monthly_duckdb.py \
      -v

Tüm süit: `pytest` → 319 test (314 geçer, 5 atlanır).

Bu testler şu durumları kontrol eder:

    D/W aggregation davranışı
    explicit policy zorunluluğu
    monthly preservation
    raw cumulative serilerin dışlanması
    quarterly sparse davranışı
    opsiyonel quarterly forward-fill davranışı
    gerçek D/W serilerinin policy coverage'ı
    metadata coverage
    duplicate kontrolü
    native JSON dims
    aligned DuckDB bütünlüğü

---

# 10. Baştan Sona Önerilen Çalıştırma Sırası

Tüm pipeline sıfırdan oluşturulurken aşağıdaki sırayla çalıştırılmalıdır:

    # 0. Bronze Katmanını Doğrulama / İndirme
    PYTHONPATH=backend python backend/scripts/bddk/build_bronze_bddk.py
    PYTHONPATH=backend python backend/scripts/evds/build_bronze_evds.py

    # 1. BDDK Silver Üretimi
    PYTHONPATH=backend python \
      backend/scripts/bddk/build_silver_bddk.py

    # 2. BDDK DuckDB (Opsiyonel / İnceleme Amaçlı)
    PYTHONPATH=backend python \
      backend/scripts/bddk/build_silver_duckdb.py

    # 3. EVDS Silver Üretimi
    PYTHONPATH=backend python \
      backend/scripts/evds/build_silver_evds.py \
      --full-refresh

    PYTHONPATH=backend python \
      backend/scripts/build_silver_canonical.py

    PYTHONPATH=backend python \
      backend/scripts/build_aligned_monthly.py

    # 6. Gold Katmanı Üretimi
    PYTHONPATH=backend python \
      backend/app/modules/gold/build_all_gold.py
      
    # 7. Unified Lakehouse Catalog & DuckDB Routing
    PYTHONPATH=backend python \
      backend/app/modules/gold/build_duckdb_views.py

Ardından full test suite çalıştırılmalıdır:

    PYTHONPATH=backend python -m pytest -v

Tüm süit (Gold katmanı dâhil): `pytest` → 319 test (314 geçer, 5 atlanır; atlananlar MIA_API_KEY gerektiren canlı servis testleri ve opt-in canlı web testidir).

---

# 11. Güncel Veri Mimarisi

    BDDK Bronze             EVDS Bronze
         │                       │
         ▼                       ▼
    BDDK Silver             EVDS Silver
         │                       │
         └──────────┬────────────┘
                    ▼
             Canonical Silver
             silver.duckdb
                    │
                    ▼
            Alignment Service
                    │
                    ▼
          Monthly Aligned Layer
                    │
                    ▼
                   Gold
                    │
                    ▼
             lakehouse.duckdb
         (Unified Lakehouse Router)

---

# 12. Temel Mimari Kararlar

1. Source-specific Silver katmanlarında doğal veri frekansı korunur.

2. Canonical Silver katmanı kaynakları ortak bir şemaya getirir ancak kaynak semantiğini bozmaz.

3. Alignment işlemi explicit policy ile yapılır.

4. Haftalık BDDK bilanço ve bakiye verileri aylık oluşturulurken toplanmaz; ay içerisindeki son observation kullanılır.

5. Raw cumulative / YTD veriler aylık flow gibi kullanılmaz.

6. Quarterly veriler otomatik olarak aylık verilere dönüştürülmez.

7. Reusable business logic `backend/app/services/` altında tutulur.

8. Pipeline çalıştıran batch scriptleri `backend/scripts/` altında tutulur.

9. Generated analytical artifacts kaynak verilerden ve scriptlerden tekrar üretilebilir olmalıdır.

10. LLM veya API normal kullanımda alignment işlemini her request sırasında yeniden çalıştırmamalıdır.

11. Alignment işlemi veri güncellendiğinde batch olarak çalıştırılmalı ve LLM/API hazır analytical veriyi kullanmalıdır.

---

# 13. Gold Öncesi Güncel Durum

Şu anda tamamlanan katmanlar:

    BDDK Bronze
        ✅

    BDDK Silver
        ✅

    EVDS Silver
        ✅
        Not: mevcut Bronze coverage ayrıca raporlanmaktadır.

    Canonical Silver
        ✅

    Canonical schema validation
        ✅

    Central silver.duckdb
        ✅

    Parquet naming standardizasyonu
        ✅

    FinTürk geography normalization
        ✅

    Alignment Service
        ✅

    Alignment Policies
        ✅

    Monthly Aligned Layer
        ✅

    Alignment regression tests
        ✅

    Gold Core Tables (build_all_gold.py)
        ✅

    Unified Lakehouse & Data Catalog (lakehouse.duckdb)
        ✅

    Semantik Seri Vektör Kataloğu (series_embeddings.parquet)
        ✅

---

# 14. Semantik Seri Embedding Kataloğunu Üretme (Gold)

LLM Ajanının Lakehouse'daki 963 finansal zaman serisini doğal dil ile (kod bilmeden) arayabilmesi için Qwen3-Embedding-8B modeliyle vektör kataloğu oluşturulur.

### Çalıştırma Komutu:
```powershell
# Windows (PowerShell):
$env:PYTHONPATH="backend"; .venv\Scripts\python backend/scripts/generate_catalog_embeddings.py

# Linux / macOS (Bash):
PYTHONPATH=backend python backend/scripts/generate_catalog_embeddings.py
```

* **Girdi:** `data/silver/silver.duckdb` (`series_metadata`, `observations`) ve `data/bronze/evds/metadata_raw.json`.
* **Çıktı:** `data/gold/series_embeddings.parquet` (963 satır, 4096 boyutlu vektörler + zengin metadata).
* **Süre:** Kloudeks batch API ile ~70 saniye.
* **Kullanan Araç:** `backend/app/tools/series_catalog_search.py` (<0.15s gecikme ile arama yapar).

---

# 15. Dinamik Ajan ve Tool Testleri (`scripts/test_dynamic_tools.py`)

Ajanın doğru araçları seçtiğini, LLM karar sürelerini ve tool yanıtlarını ölçmek için uçtan uca dinamik test suite'i kullanılır.

### Testleri Çalıştırma:
```powershell
# Belirli senaryoları çalıştırmak için (örn: 7.5, 7.6 ve 8.1):
.venv\Scripts\python scripts/test_dynamic_tools.py 7.5 7.6 8.1

# Tüm senaryoları çalıştırmak için:
.venv\Scripts\python scripts/test_dynamic_tools.py
```
* **Rapor Çıktısı:** `reports/dynamic_tools_timing_report.json` dosyasına her adımın (LLM karar süresi, tool süresi, toplam süre) metrikleri kaydedilir.

### Yeni Test Senaryosu Nasıl Eklenir?
`scripts/test_dynamic_tools.py` dosyasındaki `TEST_SCENARIOS` listesine aşağıdaki formatta bir sözlük eklemeniz yeterlidir:

```python
{
    "id": "8.4",                                    # Benzersiz senaryo ID'si
    "tool_class": "EvdsTool",                       # İlgili Tool sınıfı adı (raporlama için)
    "expected_tool": "evds_data_service",           # Ajanın çağırması beklenen tool adı
    "prompt": "Kullanıcının soracağı doğal dil sorusu buraya yazılır.",
},
```

> **İpucu:** Soruları teknik meta dille değil (*"veritabanında şu seri var mı"* gibi), gerçek bir kullanıcının sorabileceği doğal finansal sorular olarak yazın (*"Merkez Bankası'nın brüt rezervi ne kadar?"* gibi).

