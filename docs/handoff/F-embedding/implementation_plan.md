# Uygulama Planı: Qwen3-Embedding-8B ile Semantik Seri Arama Aracı (`series_catalog_search`)

Sistemimizde bulunan **963 adet zaman serisini** (BDDK, EVDS, TÜİK, BIST) `Qwen3-Embedding-8B` modeli ile vektörleştiren, doğal dille sorulan finansal kavramları (örn: *"araba kredisi"*, *"enflasyon sepeti"*, *"İstanbul gayrinakdi kredi"*) milisaniyeler içinde doğru `series_id` ile eşleştiren ve sistemde olmayan veriler için canlı EVDS servisine yönlendiren **`series_catalog_search`** aracının geliştirilmesi.

---

## 1. Kullanıcı İncelemesi ve Mimari Kararlar

> [!IMPORTANT]
> - **Zengin Semantik Kimlik Kartı:** Sadece seri adı ve kategori değil; kaynak kurum (`source`), frekans (`freq`), finansal nitelik (`nature: stock/flow`), İngilizce karşılık (`series_name_eng`), gözlem tarih aralığı (`start_date - end_date`), gözlem sayısı (`obs_count`) ve boyut kırılımları (`dims`) vektörleştirme metnine dahil edilecektir.
> - **Vektör Dosyası Konumu:** `data/gold/series_embeddings.parquet` olarak Gold katmanında kalıcı Feature Store olarak saklanacak (toplam ~15 MB). DuckDB içine View olarak eklenmeyip doğrudan Tool tarafından bellekte (Numpy float32) tutulacak; böylece kosinüs benzerliği **1 milisaniyede** tamamlanacak.
> - **Çift Kademeli Akıllı Yönlendirme (Smart Threshold):** Benzerlik skoru eşiğin (örn: %45) altında kalırsa, araç ajana *"Bu veri yerel Lakehouse'da bulunamadı; lütfen harici EVDS veri servisini (`evds_data_service`) deneyin"* mesajı döndürerek 3. Tool ile kusursuz bir köprü kuracak.

---

## 2. Yapılacak Değişiklikler ve Dosya Planı

### A. Çevrimdışı Zengin Vektörleştirme Scripti
#### [NEW] [generate_catalog_embeddings.py](file:///c:/Projects/kkb/backend/scripts/generate_catalog_embeddings.py)
* **Veri Birleştirme (Join):**
  1. `data/silver/silver.duckdb` içindeki `series_metadata` (963 seri) tablosunu okur.
  2. `observations` tablosu ile aggregate join yaparak her serinin `min(date)`, `max(date)` ve `count(*)` değerlerini alır.
  3. `data/bronze/evds/metadata_raw.json` dosyasından EVDS serilerinin `SERIE_NAME_ENG`, `DATAGROUP_NAME`, `NOTE` alanlarını eşleştirir.
* **Zenginleştirilmiş Semantik Metin Şablonu:**
  ```text
  Kaynak Kurum: {source} | Frekans: {freq} | Nitelik: {nature}
  Seri Kodu: {series_code} | Seri ID: {series_id}
  Seri Adı: {series_name} | İngilizce Adı: {series_name_eng}
  Kategori & Veri Grubu: {category} - {datagroup_name}
  Birim: {unit} | Gözlem Sayısı: {obs_count} | Tarih Aralığı: {start_date} - {end_date}
  Boyut Kırılımları: {dims_summary}
  Açıklama / Metodoloji Notu: {description}
  Etiketler: {tags}
  ```
* `KloudeksProvider.embed()` kullanarak 64'lük batch'ler halinde 4096 boyutlu embedding vektörlerini alır.
* Çıktıyı `data/gold/series_embeddings.parquet` içine yazar:
  - `series_id` (VARCHAR)
  - `series_code` (VARCHAR)
  - `source` (VARCHAR - EVDS, BDDK_MONTHLY, BDDK_WEEKLY, BDDK_FINTURK)
  - `freq` (VARCHAR - D, W, M, Q)
  - `nature` (VARCHAR - stock, flow)
  - `series_name` (VARCHAR)
  - `series_name_eng` (VARCHAR)
  - `category` (VARCHAR)
  - `unit` (VARCHAR)
  - `start_date` (VARCHAR)
  - `end_date` (VARCHAR)
  - `obs_count` (INTEGER)
  - `dims_summary` (VARCHAR)
  - `description` (VARCHAR)
  - `tags` (VARCHAR[])
  - `embedding` (LIST of FLOAT / FLOAT[4096])

---

### B. Semantik Seri Arama Aracı
#### [NEW] [series_catalog_search.py](file:///c:/Projects/kkb/backend/app/tools/series_catalog_search.py)
`tool_sozlesmesi_prompt.md` standartlarına tam uyumlu `BaseTool` sınıfı:
* **Tool Adı:** `series_catalog_search`
* **Girdi Parametreleri (`Input`):**
  - `query`: Kullanıcının doğal dille sorduğu finansal kavram (örn: *"taşıt kredisi faizleri"*, *"İstanbul gayrinakdi krediler"*, *"enflasyon sepeti"*, *"brüt rezerv"*).
  - `top_k`: Döndürülecek en alakalı maksimum seri sayısı (varsayılan: `5`, max: `20`).
  - `threshold`: Minimum benzerlik eşiği (varsayılan: `0.45`).
* **Çalışma Mantığı:**
  1. Başlangıçta parquet dosyasındaki vektörleri `numpy` 2D array (`963 x 4096`) olarak belleğe alır.
  2. `provider.embed([query])` ile kullanıcının sorgusunun vektörünü alır.
  3. Matris kosinüs benzerliği uygular: `scores = np.dot(matrix, query_vec) / (norms * query_norm)`.
  4. En yüksek skorlu `top_k` seriyi sıralar.
* **Çıktı Modeli (`Output`):**
  - `success`: `bool`
  - `query`: `str`
  - `found_in_lakehouse`: `bool` (Eşik değerini aşan seri bulundu mu?)
  - `best_match_score`: `float`
  - `matches`: `list[SeriesMatch]` (her bir seri için `series_id`, `series_code`, `series_name`, `source`, `category`, `unit`, `freq`, `date_range`, `similarity_score`, `recommended_tool`)
  - `suggestion`: Sistemde yoksa EVDS canlı servisine yönlendiren rehber mesaj.

---

### C. Ajan Döngüsü ve Sistem Prompt Güncellemesi
#### [MODIFY] [loop.py](file:///c:/Projects/kkb/backend/app/agent/loop.py)
* Sistem promptuna eklenecek strateji kuralı:
  > *"Kullanıcı belirli bir finansal gösterge, kredi türü, faiz, sektör veya makroekonomik veri sorduğunda, eğer tam `series_id` kodundan emin değilsen önce `series_catalog_search` aracını kullanarak sistemde bu seriyi ara. Dönen seriler üzerinden `lakehouse_query` veya `change_detection` çağrısı yap. Eğer araç serinin sistemde bulunamadığını belirtirse, harici veri çekmek için `evds_data_service` veya `web_search` araçlarına başvur."*

---

### D. Birim Testler ve Doğrulama
#### [NEW] [test_series_catalog_search.py](file:///c:/Projects/kkb/backend/tests/tools/test_series_catalog_search.py)
1. **Mock Embedding Testi:** Sahte vektörlerle kosinüs benzerliği sıralamasının ve zengin alanların doğrulanması.
2. **Eşik Altı (Not Found) Testi:** Alakasız bir sorguda `found_in_lakehouse=False` ve EVDS yönlendirme mesajının teyidi.
3. **Pydantic Şema & Tool Registry Testi:** OpenAPI JSON şeması ve zorunlu alan kontrolü.

#### [MODIFY] [test_dynamic_tools.py](file:///c:/Projects/kkb/scripts/test_dynamic_tools.py)
* **Senaryo 7.1:** *"Taşıt kredisi hacmi ve faizleri için hangi serileri kullanabilirim?"* -> `series_catalog_search` çalışır ve `BDDK_MONTHLY:..._tasit` serisini yüksek benzerlikle döner.
* **Senaryo 7.2:** Sistemde olmayan bir sorgu (örn: *"Platin fiyatı ve Londra metal borsası"*): Düşük skor üretip EVDS yönlendirmesi yapar.

---

## 3. Doğrulama Planı

1. **Vektör Üretimi Doğrulaması:**
   ```powershell
   .venv\Scripts\python backend\scripts\generate_catalog_embeddings.py
   # data/gold/series_embeddings.parquet dosyasının oluştuğu, 963 satır içerdiği ve tüm zengin kolonların dolduğu doğrulanır.
   ```
2. **Otomatik Birim Testleri:**
   ```powershell
   $env:PYTHONPATH="backend"; .venv\Scripts\python -m pytest backend/tests/tools/test_series_catalog_search.py -v
   ```
3. **Tüm Test Paketinin Regresyon Doğrulaması:**
   ```powershell
   $env:PYTHONPATH="backend"; .venv\Scripts\python -m pytest backend/tests -q
   ```
4. **Canlı Ajan Senaryosu Doğrulaması:**
   ```powershell
   $env:PYTHONPATH="backend"; .venv\Scripts\python scripts/test_dynamic_tools.py 7.1 7.2
   ```
