# Canlı Veri & Silver Katmanı Analitik Fallback İmplementasyon Planı

> **Hedef Dizin:** `backend/app/tools/` & `backend/app/services/`  
> **Klasör:** `docs/handoff/f-analytics-silver-fallback/`  
> **Kapsam:** `evds_data_service` ile dinamik indirilen ve `data/silver/silver.duckdb` içine kaydedilen yeni serilerin; `causality_check`, `elasticity_and_sensitivity_analyzer`, `real_value_deflator`, `turning_point_and_cycle_detector`, `change_detection` ve `anomaly_detection` analitik araçları tarafından anında okunabilmesini sağlayan **Unified DuckDB / Silver Fallback Mimarisi**.

---

## 1. Problem Tanımı ve Kök Neden Analizi

### 1.1. Yaşanan Sorun
Kullanıcı *"Mevduat faizlerindeki artışın bireysel kredi kartı borçlarına ve batık kredi riskine etkisini çok boyutlu analiz et"* sorduğunda:
1. `evds_data_service` başarıyla çalıştı ve TCMB'den `EVDS:TP.TRY.MT02.S` (TL Mevduat Faizi) serisini canlı olarak **`data/silver/silver.duckdb`** tablosuna yazdı (66 aylık gözlem).
2. Ancak model bir sonraki adımda `causality_check` ve `elasticity_and_sensitivity_analyzer` araçlarını çağırdığında:
   - Araçlar: `"Seri bulunamadi: EVDS:TP.TRY.MT02.S"` hatası döndürdü.
3. Araçlar çökünce model ekonometrik analizleri yapamadı; mecburen prompt içinde kafasından matematik yaparak:
   - *"Kredi kartı borcu 15,7 kat arttı"*, *"NPL 5,6 kat arttı"*, *"197,1 bin"*, *"601,1 bin"* gibi uydurma/yaklaşık sayılar türetti.
4. Doğruluk Kontrolü (Grounding Engine) haklı olarak alarm verdi:
   - `⚠️ 32 sayı kontrol edildi · 9 eşleşti · 23 eşleşmedi!`

### 1.2. Kök Neden (Root Cause)
* **Veri Yazma Tarafı:** `evds_loader.py` yeni indirilen serinin `nature` (stok/akım) alanı henüz manuel onaylanmadığı için (`nature_reviewed=False`, `pending_review=True`), seriyi `aligned.duckdb` katmanına aktarmayı atlıyor; sadece **`data/silver/silver.duckdb`** içine kaydediyor.
* **Veri Okuma Tarafı:** Analitik araçlarımızın tümü (`causality_check`, `elasticity_analyzer`, `real_value_deflator`, `turning_point_detector`, `change_detection`, `anomaly_detection`) diski sorgularken veritabanına bakmak yerine, sabit diske haftalar önce yazılmış **statik `.parquet` dosyalarına** (`gold_periodic_change.parquet` veya `aligned/monthly/observations.parquet`) `SELECT * FROM read_parquet(...)` ile bağlanıyor.
* **Kopukluk:** Yeni indirilen seri veritabanında (`silver.duckdb`) var, fakat statik `.parquet` dosyalarında yok! Bu yüzden analiz araçları kör kalıyor.

---

## 2. Mimari Çözüm: Unified Observation Provider (Silver Fallback)

Analitik araçların veri çekme katmanına **iki aşamalı akıllı çözümleme (Unified Fallback)** getirilecektir:

```
                          ┌───────────────────────────────┐
                          │    Analitik Araç Çağrısı      │
                          │ (causality_check, elasticity) │
                          └──────────────┬────────────────┘
                                         │
                                         ▼
                          ┌───────────────────────────────┐
                          │  1. Aşama: Statik Parquet?    │
                          │ (gold_periodic_change/aligned)│
                          └──────────────┬────────────────┘
                                         │
                          ┌──────────────┴──────────────┐
                          ▼ Seri Bulundu                ▼ Seri Bulunamadı
                 ┌─────────────────┐           ┌─────────────────────────────┐
                 │ Parquet'den Oku │           │ 2. Aşama: Canlı Fallback    │
                 │   (Hızlı Yol)   │           │  (data/silver/silver.duckdb)│
                 └─────────────────┘           └──────────────┬──────────────┘
                                                              │
                                               ┌──────────────┴──────────────┐
                                               ▼ Seri Bulundu                ▼ Bulunamadı
                                      ┌─────────────────┐           ┌──────────────────┐
                                      │ Silver'dan Oku, │           │ "Seri gerçekten │
                                      │  Gerekirse Aylık│           │  bulunamadı"     │
                                      │  Hizala & Çalış │           │  hatası dön      │
                                      └─────────────────┘           └──────────────────┘
```

---

## 3. Yapılacak Değişiklikler ve İlgili Dosyalar

### 3.1. Ortak Veri Çözümleme Servisi (`backend/app/services/series_data_resolver.py`)
Tekrarlayan kod yazmamak için analitik araçların ortak kullanacağı hafif bir helper modülü oluşturulacak:
* `get_series_observations(series_id, dimension=None, start_date=None, end_date=None)`
* Fonksiyon önce `gold_periodic_change.parquet` ve `aligned/monthly/observations.parquet` dosyalarını kontrol eder.
* Eğer `series_id` orada yoksa, anında `data/silver/silver.duckdb` tablosundaki `observations` tablosuna bakar.
* Tarihleri ve değerleri `(date, value)` formatında döner.

### 3.2. `backend/app/tools/causality_check.py`
* `_resolve_series_and_dimension` fonksiyonu: Seri `gold_periodic_change.parquet` içinde yoksa, `silver.duckdb` üzerinde arama yapar.
* SQL sorgusu: Eğer serilerden biri veya her ikisi Silver'dan geliyorsa, CTE sorgusu `read_parquet(...)` yerine `silver.duckdb` tablosuyla birleştirilerek Pearson korelasyonu ve Granger testi hesaplanır.

### 3.3. `backend/app/tools/elasticity_and_sensitivity_analyzer.py`
* `_resolve_series_id` ve veri çekme bloğu: `observations.parquet` dosyasında bulunamayan seriler `silver.duckdb`'den çekilir.
* Log-log OLS regresyonu ve saçılım grafiği Silver verisiyle de eksiksiz üretilir.

### 3.4. `backend/app/tools/real_value_deflator.py`
* Nominal seri veya deflatör serisi `observations.parquet`'de yoksa `silver.duckdb` üzerinden okunur.
* Enflasyon arındırması ve alan grafiği üretilir.

### 3.5. `backend/app/tools/turning_point_and_cycle_detector.py`
* Zaman serisi `silver.duckdb` üzerinden okunarak tepe/dip noktaları ve döngü grafiği üretilir.

### 3.6. `backend/app/tools/change_detection.py` & `anomaly_detection.py`
* Eğer seri `gold_periodic_change.parquet`'de yoksa `silver.duckdb`'den okunur; `mom_pct_change` ve `yoy_pct_change` metrikleri DuckDB'nin `LAG(value) OVER (ORDER BY date)` window fonksiyonuyla anında hesaplanır.

### 3.7. Ajan İterasyon Limiti Güncellemesi (`backend/app/api/routes.py`)
* Çok göstergeli, korelasyon ve döngü analizlerinin arka arkaya çalıştırıldığı derin araştırmalarda adım sınırına takılmayı önlemek amacıyla `AGENT_MAX_ITERATIONS` varsayılan değeri `12`'den **`15`**'e çıkarılacaktır.
* Bu sayede ajan; katalog arama -> EVDS canlı çekme -> korelasyon -> esneklik -> döngü tespiti adımlarını adım limiti engeline takılmadan rahatça tamamlayabilecektir.

---

## 4. `evds_loader.py` Dokunulmayacak (Mimari Karar)
* `evds_loader.py` dosyasındaki mevcut `nature == 'unclassified'` kuralı **kasıtlı olarak korunacaktır.**
* Canlı indirilen seriler insan incelemesinden geçmeden `aligned.duckdb` veya `gold` katmanına zorlanmamalıdır (yanlış interpolasyon riskini önlemek için).
* Veri zaten güvenle `data/silver/silver.duckdb` içine yazılmaktadır; analitik toolların doğrudan `silver.duckdb` tablosundan okuması bu mimari sözleşmeyi bozmadan sorunu çözen en temiz yöntemdir.

---

## 5. Doğrulama ve Test Planı

### 5.1. Otomatik Testler
1. `backend/tests/tools/test_analytics_silver_fallback.py`:
   - Yalnızca `silver.duckdb` içinde olan `EVDS:TP.TRY.MT02.S` serisi için:
     - `causality_check` çağrısı yapılacak -> Korelasyon katsayısı dönmeli (Hata vermemeli).
     - `elasticity_and_sensitivity_analyzer` çağrısı yapılacak -> Elastikiyet katsayısı ve grafik dönmeli.
     - `real_value_deflator` çağrısı yapılacak -> Reel büyüme dönmeli.
     - `turning_point_and_cycle_detector` çağrısı yapılacak -> Tepe/dip dönmeli.

### 5.2. Canlı Uçtan Uca Doğrulama (E2E)
* Kullanıcının sorduğu soru tekrar çalıştırılacak:
  *"Mevduat faizlerindeki artışın bireysel kredi kartı borçlarına ve batık kredi riskine etkisini çok boyutlu analiz et."*
* Beklenen Çıktı:
  - `causality_check` ve `elasticity_analyzer` başarıyla çalışacak.
  - LLM kafasından "15,7 kat", "5,6 kat" uydurmak yerine toolların ürettiği gerçek korelasyon ve esneklik katsayılarını rapora yazacak.
  - **Doğruluk Kontrolü:** `⚠️ 23 eşleşmedi` yerine **✅ Hepsi eşleşti** olacak!
