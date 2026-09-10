# F-003: EVDS & BDDK Entegrasyonu, Alignment ve Test Yapılacaklar Listesi

> **Durum:** EVDS ve BDDK Silver katmanları tamamlandı, Canonical Silver (`silver.duckdb`) üretildi. Aylık Hizalama (`build_aligned_monthly.py`) ve Test adımları için uygulanacak aksiyon planı aşağıda tanımlanmıştır.

---

## 1. Mevcut Durum Özeti (GÜNCEL: TÜMÜ TAMAMLANDI ✅)

| Katman / Bileşen | Durum | Gözlem (Satır) | Seri Sayısı | Notlar |
|---|---|---|---|---|
| **EVDS Silver** (`data/silver/evds/`) | ✅ Tamamlandı | 25.386 | 118 | %100 doluluk, 12 D + 12 W + 94 M serisi |
| **BDDK Silver** (`data/silver/bddk/`) | ✅ Tamamlandı | 426.367 | 845 | 188 W + 581 M + 76 Q serisi |
| **Canonical Silver** (`silver.duckdb`) | ✅ Tamamlandı | 451.753 | 963 | 0 duplicate, 0 eksik metadata |
| **Monthly Aligned** (`aligned.duckdb`) | ✅ Tamamlandı | 311.704 | 917 | 212 D/W serisi (188 BDDK `last`, 24 EVDS `mean`) |
| **Test Suite** (`pytest`) | ✅ %100 Başarılı | - | - | **119 testin 119'u da PASSED** (0 failed) |

---

## 2. Tespit Edilen Kök Sorun ve "Neden Mean?" Analizi

### Sorun Tanımı
`backend/scripts/build_aligned_monthly.py` çalıştırıldığında şu hata fırlatılmaktadır:
```text
ValueError: Missing explicit alignment policies for 15 D/W series:
EVDS:TP.ALTINPIYASA.KAP02, EVDS:TP.ALTINPIYASA.KAP03, EVDS:TP.DK.CHF.A.YTL,
EVDS:TP.DK.EUR.S.YTL, EVDS:TP.DK.GBP.A.YTL, EVDS:TP.DK.JPY.A.YTL,
EVDS:TP.DK.USD.S.YTL, EVDS:TP.EUR.MT02, EVDS:TP.GUMUSPIYASA.KAP03,
EVDS:TP.TRY.MT01, EVDS:TP.TRY.MT03, EVDS:TP.TRY.MT04,
EVDS:TP.TRY.MT05, EVDS:TP.TRY.MT06, EVDS:TP.USD.MT02
```

### Neden `method="mean"` (Aylık Ortalama) Kullanılmalıdır?
1. **İktisadi Mantık (Stok vs. Oran/Fiyat):**
   - **Stok Bakiye (BDDK - Krediler/Mevduatlar):** Ay sonundaki toplam finansal riski görmek için ayın son gözlemi (`last`) alınır.
   - **Oran ve Fiyat (EVDS - Faizler, Kurlar, Madenler):** Faiz ve döviz kurları bir "seviye/oran" göstergesidir. Ayın son günü oluşabilecek anlık spekülatif veya likidite kaynaklı dalgalanmalar tüm ayı temsil edemez. Makroekonomik ve kredi risk modellerinde (Gold feature store) bir ayın borçlanma maliyeti ve kur seviyesi **aylık ortalama (`mean`)** ile temsil edilir.
2. **Mimari Kural Uyumu (`SETUP.md`):**
   - Ekip arkadaşı Mert tarafından `SETUP.md` dosyasında belgelenen resmi kural:
     - *EVDS günlük döviz kuru serileri $\rightarrow$ monthly mean*
     - *EVDS haftalık faiz oranları $\rightarrow$ monthly mean*
     - *EVDS günlük TCMB fonlama göstergeleri $\rightarrow$ monthly mean*
3. **Mevcut Test Zorunluluğu (`test_aligned_monthly_duckdb.py`):**
   - `test_evds_daily_and_weekly_use_mean()` testi, EVDS kaynaklı tüm D ve W serilerinin `alignment_method == 'mean'` olmasını zorunlu kılmaktadır. Farklı bir yöntem doğrudan testin başarısız olmasına yol açar.

---

## 3. Adım Adım Yapılacaklar Listesi

### Adım 1: `alignment_policies.py` Güncellemesi
* **Dosya:** [alignment_policies.py](file:///c:/Projects/kkb/backend/app/services/alignment_policies.py)
* **Yapılacak İşlem:** `EVDS_ALIGNMENT_POLICIES` sözlüğüne eksik kalan 15 D ve W serisini `AlignmentPolicy(method="mean")` olarak eklemek veya EVDS D/W serilerini kapsayan kuralı eksiksiz tamamlamak.
* **Kapsanacak 24 EVDS D/W Serisi:**
  - **Döviz Kurları (D):** `TP.DK.USD.A.YTL`, `TP.DK.USD.S.YTL`, `TP.DK.EUR.A.YTL`, `TP.DK.EUR.S.YTL`, `TP.DK.GBP.A.YTL`, `TP.DK.JPY.A.YTL`, `TP.DK.CHF.A.YTL`
  - **TCMB Fonlama Oranları (D):** `TP.APIFON1.IHA`, `TP.APIFON4`
  - **Kıymetli Maden Fiyatları (D):** `TP.ALTINPIYASA.KAP02`, `TP.ALTINPIYASA.KAP03`, `TP.GUMUSPIYASA.KAP03`
  - **Kredi Faiz Oranları (W):** `TP.KTF10` (Taşıt), `TP.KTF11` (Konut), `TP.KTF12` (İhtiyaç), `TP.KTF17` (Ticari)
  - **TL Mevduat Faiz Oranları (W):** `TP.TRY.MT01`, `TP.TRY.MT02`, `TP.TRY.MT03`, `TP.TRY.MT04`, `TP.TRY.MT05`, `TP.TRY.MT06`
  - **YP Mevduat Faiz Oranları (W):** `TP.USD.MT02`, `TP.EUR.MT02`

### Adım 2: `test_alignment_policies.py` Test Kontrolünün Güncellenmesi
* **Dosya:** [test_alignment_policies.py](file:///c:/Projects/kkb/backend/tests/services/test_alignment_policies.py)
* **Yapılacak İşlem:** Mert'in test yazarken kendi elindeki eski 9 EVDS serisine göre hardcode ettiği `assert len(metadata) == 197` ifadesini, 118 serilik tam EVDS setimizdeki güncel D/W serisi sayısıyla (188 BDDK + 24 EVDS = 212 seri) uyumlu hale getirmek:
  ```python
  assert len(metadata) == 212
  assert len(policies) == 212
  assert set(policies) == set(metadata["series_id"])
  ```

### Adım 3: Aylık Hizalama Scriptinin Çalıştırılması
* **Komut:**
  ```powershell
  .venv\Scripts\python backend/scripts/build_aligned_monthly.py
  ```
* **Beklenen Çıktılar:**
  - `data/aligned/monthly/observations.parquet`
  - `data/aligned/monthly/series_metadata.parquet`
  - `data/aligned/monthly/aligned.duckdb`

### Adım 4: Tüm Test Paketinin Koşturulması (Pytest Verification)
* **Komut:**
  ```powershell
  .venv\Scripts\pytest -v
  ```
* **Hedef Metrik:** 119 testin 119'unun da (%100) **PASSED** vermesi.

### Adım 5: Dokümantasyonun Güncellenmesi
* `SETUP.md` dosyasındaki seri ve observation sayılarını tam set doğrulanmış sonuçlarla güncellemek.
* `notlar/potansiyel_sorunlar_evds_bddk.md` dosyasında çözülen maddeleri işaretlemek.
