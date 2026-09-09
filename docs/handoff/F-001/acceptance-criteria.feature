Feature: F-001 EVDS Veri Temini (Bronze Katmanı)
  Dependencies: T-08, ADR-0001

  Scenario: [Happy Path] Ilk indirme isleminde tum serilerin JSON dosyalarinin basariyla uretilmesi (BR-01, BR-02, BR-03, BR-06, BR-07, BR-08)
    Given "backend/app/modules/evds/series_manifest.yaml" dosyasi 4 cekirdek seri (TP.KTF10, TP.FG.J0, TP.HKFE01, TP.DK.USD.A.YTL) tanimlari icerdiginde
    And "data/bronze/evds" dizini tamamen bos oldugunda
    When "python backend/scripts/seed_evds.py" komutu calistirildiginda
    Then islem 0 donus kodu (exit code 0) ile basariyla tamamlanmalidir
    And "data/bronze/evds/" dizininde "TP.KTF10.json", "TP.FG.J0.json", "TP.HKFE01.json" ve "TP.DK.USD.A.YTL.json" dosyalari olusmalidir
    And uretilen dosyalarin icerigi ham JSON veri yapisina ("raw=True") sahip olmalidir

  Scenario: [Boundary/Edge Case] Idempotency kontrolu ile mevcut dosyalarin indirilmesinin atlanmasi (BR-04)
    Given "data/bronze/evds/TP.KTF10.json" dosyasi daha onceden basariyla indirilmis ve dolu (boyut > 0) oldugunda
    When "python backend/scripts/seed_evds.py" komutu calistirildiginda
    Then sistem "TP.KTF10.json" dosyasi icin yeni bir API istegi yapmamalidir
    And konsol ciktisinda "TP.KTF10" icin "[SKIP]" logu basilmalidir
    And islem diger serileri indirmeye devam etmelidir

  Scenario: [Error Case / Edge Case] Rate Limit asildiginda anahtar rotasyonu (BR-05)
    Given API istekleri "EVDS_API_KEY_1" anahtari ile yapilirken "HTTP 429" (Rate Limit) hatasi alindiginda
    And `.env` dosyasinda bir sonraki anahtar olan "EVDS_API_KEY_2" tanimli oldugunda
    When sistem otomatik olarak siradaki anahtara gectiginde
    Then islem iptal olmadan "EVDS_API_KEY_2" ile istegi tekrarlamalidir
    And ilgili seri ham JSON olarak basariyla indirilmelidir

  Scenario: [Error Case] Yonerge dosyasinin bozuk formatta olmasi durumunda firlatilacak hata (BR-02)
    Given "backend/app/modules/evds/series_manifest.yaml" dosyasi hatali YAML formatinda veya bulunamiyor oldugunda
    When "python backend/scripts/seed_evds.py" komutu calistirildiginda
    Then islem sifir olmayan (non-zero) bir donus kodu (exit code) vermelidir
    And konsolda dosyanin okunamadigina veya parse edilemedigine dair hata mesaji goruntulenmelidir
    And "data/bronze/evds/" dizinine herhangi bir seri dosyasi kaydedilmemelidir

  Scenario: [Happy Path] Keşif işlemi ile kataloğun başarıyla oluşturulması (BR-06)
    Given "data/bronze/evds/evds_catalog.parquet" dosyası henüz mevcut olmadığında
    When "python backend/scripts/seed_catalog.py" komutu çalıştırıldığında
    Then işlem başarıyla tamamlanmalıdır (exit code 0)
    And "data/bronze/evds/evds_catalog.parquet" dosyası oluşturulmalıdır
    And dosya tüm kategorileri, alt kategorileri ve serileri içeren geçerli bir parquet formatında olmalıdır

  Scenario: [Happy Path] İndirme işlemi sonrasında kataloğun güncellenmesi (BR-06, BR-07)
    Given "data/bronze/evds/evds_catalog.parquet" kataloğunda "TP.KTF10" serisi "is_ingested=False" olarak kayıtlı olduğunda
    When "python backend/scripts/seed_evds.py" komutu çalıştırılıp "TP.KTF10" başarıyla indirildiğinde
    Then "catalog_store.py" üzerinden ilgili parquet kaydı güncellenmelidir
    And katalogda "TP.KTF10" serisi için "is_ingested=True" ve "fetch_status='SUCCESS'" olarak işaretlenmelidir
