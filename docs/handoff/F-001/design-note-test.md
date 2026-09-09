# Design Note (Test) — F-001

Status: complete

## Test Strategy & Scenarios
- `pytest` kullanılarak unit testler tasarlanacaktır.
- **Harici Servis Mock'u:** `evds` pip paketinin dış API çağrıları mock'lanacaktır.
- **Dosya Sistemi Mock'u:** Disk okuma/yazma (JSON ve Parquet) işlemlerinde geçici dizinler (`tmp_path`) kullanılacaktır. `pandas` veya Parquet motoru mock'lanmadan doğrudan sanal dosya sistemine yazılması tercih edilir (gerçek davranışı görmek için).
- **Environment Mock'u:** `.env` değişkenleri mock üzerinden sağlanacaktır.

## Mock Data Requirements
- `series_manifest.yaml`: En az 1 geçerli seriyi (örn. `TP.KTF10`) içeren test fixture'ı.
- `series_manifest_invalid.yaml`: YAML yapısı bozuk test fixture'ı.
- `evds_response_mock.json`: `evds.get_data` için ham JSON çıktısı mock'u.
- `evds_catalog_mock`: API'den dönecek kategori ve seri listesi cevaplarını mocklamak için JSON dizileri.
- `Exception` mock'u: `HTTP 429 Too Many Requests` simülasyonu.

## Task breakdown (Testing)
- T1_TEST: Katalog Oluşturma ve Ortak Store Testleri (BR-06, BR-07, BR-10) — servis ettiği: `Scenario 5`, `Scenario 6` — dosyalar: `backend/tests/modules/evds/test_catalog.py`
  - Parquet dosyasının baştan oluşturulmasını (discover_all) test eden senaryo.
  - Ortak depolama aracı (`catalog_store.py`) üzerinden `is_ingested` flag'inin başarılı şekilde güncellenebildiğini kontrol eden upsert/update testi.
- T2_TEST: Ingestion ve Idempotency Davranış Testleri (BR-03, BR-04) — servis ettiği: `Scenario 1`, `Scenario 2`, `Scenario 4`, `Scenario 6` — dosyalar: `backend/tests/modules/evds/test_ingestion.py`
  - Dizin boşken ham JSON içeriğiyle dosya oluşması testi.
  - Disk üzerindeki mevcut dosya kontrol edilerek API çağrısının atlanması testi.
  - Hatalı manifest dosyası hata yönetimi.
  - **YENİ:** Başarılı indirme sonrası katalogdaki kayıtların güncellenmesi çağrısının yapıldığının (mock `catalog_store`) doğrulanması.
- T3_TEST: İstemci ve Key Rotasyonu Testleri (BR-05) — servis ettiği: `Scenario 3` — dosyalar: `backend/tests/modules/evds/test_client.py`
  - HTTP 429 hatasında sıradaki API anahtarına geçişin test edilmesi.

## Coverage check (Testing)
- Scenario 1 (Happy Path - Indirme) → T2_TEST ✓
- Scenario 2 (Idempotency - Atlama) → T2_TEST ✓
- Scenario 3 (Key Rotation) → T3_TEST ✓
- Scenario 4 (Manifest Format Error) → T2_TEST ✓
- Scenario 5 (Keşif - Katalog Oluşturma) → T1_TEST ✓
- Scenario 6 (Katalog Güncelleme) → T1_TEST, T2_TEST ✓
