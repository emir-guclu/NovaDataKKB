# İleri Düzey Analitik Araçlar & Otomatik Grafik Görselleştirme İmplementasyon Planı

> **Hedef Dizin:** `backend/app/tools/` & `backend/app/services/`  
> **Klasör:** `f-analitic-tools`  
> **Kapsam:** Ham veri/sayı okuyucusundan **"Yönetici Düzeyinde Finansal Analist"** seviyesine geçiş sağlayan 4 temel analitik araç ve her araç için **otomatik yüksek çözünürlüklü grafik görselleştirme motoru**.

---

## 1. Genel Mimari ve Görselleştirme Akışı

NOVA'nın mevcut araç seti veri çekme ve temel istatistik işlemlerini yapabilmektedir. Bu fazda, karar vericilere yönelik **derin finansal & ekonometrik içgörüler** üretebilmek için aşağıdaki 4 uzmanlaşmış analitik araç ve ortak görselleştirme motoru (`chart_generator.py`) entegre edilecektir:

```
                  ┌──────────────────────────────────────────────┐
                  │          NOVA Agent Core (loop.py)           │
                  └──────────────────────┬───────────────────────┘
                                         │
       ┌──────────────────┬──────────────┴─────┬──────────────────┐
       ▼                  ▼                    ▼                  ▼
┌──────────────┐   ┌──────────────┐     ┌──────────────┐   ┌──────────────┐
│  Real Value  │   │  Elasticity  │     │     Risk     │   │Turning Point │
│   Deflator   │   │ & Sensitivity│     │Concentration │   │   & Cycle    │
│  (Enflasyon  │   │  (Duyarlılık │     │  (CR3/CR5 &  │   │ (Zirve/Dip & │
│ Arındırma)   │   │  Analizi)    │     │  HHI İndeks) │   │ Rejim Kırıl) │
└──────┬───────┘   └──────┬───────┘     └──────┬───────┘   └──────┬───────┘
       │                  │                    │                  │
       └──────────────────┴──────────────┬─────┴──────────────────┘
                                         │  (Matplotlib Agg Engine)
                                         ▼
                   ┌──────────────────────────────────────────┐
                   │    ChartGenerator (chart_generator.py)   │
                   └─────────────────────┬────────────────────┘
                                         │
                         ┌───────────────┴───────────────┐
                         ▼                               ▼
                 `/static/charts/`              JSON Output & LLM
            (Yüksek Çözünürlüklü PNG)       `![Grafik](/static/charts/...)`
```

---

## 2. Ortak Grafik Görselleştirme Servisi (`chart_generator.py`)

* **Dosya:** `backend/app/services/chart_generator.py`
* **Altyapı:** `matplotlib` (`Agg` non-interactive thread-safe backend) + `seaborn-v0_8-whitegrid` / modern dark-light palette.
* **Standartlar:**
  - `DPI = 150` (Retina / yüksek netlik).
  - Modern renk paleti: Zümrüt yeşili (`#10b981`), Kobalt mavisi (`#3b82f6`), Mercan kırmızısı (`#ef4444`), Kömür gri (`#1e293b`).
  - Türkçe karakter ve tarih ekseni otomatik biçimlendirme (`format_dates`).
  - Çıktı dizini: `backend/static/charts/<tool_name>_<YYYYMMDD_HHMMSS>_<hash>.png`.
  - HTTP Erişim URL'i: `/static/charts/<dosya_adi>.png`.

---

## 3. Geliştirilecek 4 Analitik Araç ve Grafik Tipleri

### 3.1. `real_value_deflator` (Enflasyondan Arındırma & Reel Büyüme)
* **Problem:** Nominal kredi/mevduat %60 büyümüş görünürken TÜFE %65 olduğunda reel küçülme (%3.1 daralma) yaşanmaktadır. Ajanın bunu otomatik tespit etmesi ve görselleştirmesi gerekir.
* **Dosya:** `backend/app/tools/real_value_deflator.py`
* **Matematiksel Formül:**
  $$Real\_Value_t = Nominal\_Value_t \times \frac{CPI_{base}}{CPI_t}$$
  $$Reel\ Büyüme\ (\%) = \left( \frac{1 + Nominal\_Büyüme}{1 + Enflasyon} - 1 \right) \times 100$$
* **Grafik:** **Nominal vs Reel Çizgi & Enflasyon Erozyonu Alanı (Area / Line Chart)**
  - *Mavi Çizgi:* Nominal Değer.
  - *Yeşil/Kırmızı Çizgi:* Enflasyondan arındırılmış Reel Değer.
  - *Gölgeli Alan (Shading):* Enflasyon kaynaklı sermaye erimesi / satın alma gücü kaybı.
* **Girdi & Çıktı:**
  ```python
  class Input(BaseModel):
      nominal_series_id: str = Field(description="Enflasyondan arındırılacak serinin ID'si")
      deflator_series_id: str = Field(default="TP.GENENDEKS.T1", description="Deflatör serisi (varsayılan: TÜFE)")
      dimension: str | None = Field(default=None)
      base_date: str | None = None
      start_date: str | None = None
      end_date: str | None = None
  ```
  - Çıktıda: `nominal_growth_pct`, `inflation_pct`, `real_growth_pct`, `erosion_amount`, `summary_verdict`, `chart_url`.

---

### 3.2. `elasticity_and_sensitivity_analyzer` (Faiz & Kur Duyarlılığı / Esneklik)
* **Problem:** Faiz artışının konut veya tüketici kredisi talebini yüzde kaç esnettiğini (esneklik katsayısını) hesaplayıp görselleştirmek.
* **Dosya:** `backend/app/tools/elasticity_and_sensitivity_analyzer.py`
* **Matematiksel Formül:**
  $$Arc\ Elasticity = \frac{\% \Delta Y}{\% \Delta X} = \frac{(Y_2 - Y_1) / \bar{Y}}{(X_2 - X_1) / \bar{X}}$$
  $$OLS\ Log-Log\ Elasticity: \ln(Y_t) = \alpha + \beta \ln(X_{t-k}) + \epsilon_t \implies \beta = \text{Esneklik Katsayısı}$$
* **Grafik:** **Serpme Grafiği ve Ekonometrik Regresyon Doğrusu (Scatter & Trendline Plot)**
  - *Noktalar (Scatter):* Faiz değişimi vs Kredi büyümesi gözlemleri.
  - *Kırmızı/Mavi Doğru:* OLS Fit regresyon eğrisi.
  - *Bilgi Kutusu:* $\beta = -1.45$ (Yüksek Esneklik), $R^2 = 0.78$.
* **Girdi & Çıktı:**
  ```python
  class Input(BaseModel):
      dependent_series_id: str = Field(description="Bağımlı değişken (örn. Konut Kredisi)")
      independent_series_id: str = Field(description="Bağımsız değişken (örn. Politika Faizi)")
      lag_months: int = Field(default=0, description="Gecikme süresi (ay)")
      method: Literal["arc_elasticity", "log_log_regression"] = "log_log_regression"
      start_date: str | None = None
      end_date: str | None = None
  ```
  - Çıktıda: `elasticity_coefficient`, `r_squared`, `classification`, `interpretation`, `chart_url`.

---

### 3.3. `risk_concentration_analyzer` (Bölgesel & Sektörel Risk / HHI & CR Yoğunlaşma)
* **Problem:** FinTÜRK ve sektörel tablolarda batık kredi (NPL) riskinin hangi illerde/sektörlerde yoğunlaştığını ve HHI risk derecesini hesaplamak.
* **Dosya:** `backend/app/tools/risk_concentration_analyzer.py`
* **Matematiksel Formül:**
  - **CR_k:** $CR_k = \sum_{i=1}^k s_i$ (İlk $k$ ilin toplam riske payı)
  - **Herfindahl-Hirschman Endeksi (HHI):** $HHI = \sum_{i=1}^N (s_i \times 100)^2$
* **Grafik:** **Sıralı Bar Grafiği & Kümülatif Lorenz Yoğunlaşma Eğrisi (Pareto Bar + Line)**
  - *Barlar:* İlk 10 ilin/sektörün risk hacmi ve yüzdesi.
  - *İkincil Eksen Çizgisi:* Kümülatif toplam payı (%CR3 ve %CR5 kesikli referans çizgileri).
  - *HHI Rozeti:* "HHI: 2150 (Orta-Yüksek Yoğunlaşma)".
* **Girdi & Çıktı:**
  ```python
  class Input(BaseModel):
      table_name: str = Field(default="gold_finturk", description="DuckDB tablosu")
      dimension_column: str = Field(default="city_name", description="Analiz boyutu")
      metric_column: str = Field(description="Metrik sütunu (örn. npl_amount)")
      date: str | None = None
      top_k: int = Field(default=5)
  ```
  - Çıktıda: `cr3_share_pct`, `cr5_share_pct`, `hhi_score`, `top_entities`, `fastest_deteriorating`, `chart_url`.

---

### 3.4. `turning_point_and_cycle_detector` (Dönüm Noktası & Trend/Rejim Kırılımı)
* **Problem:** Zaman serisindeki tepe (zirve) ve dip noktalarını, daralma/genişleme döngü sürelerini ve trend kırılımlarını belirlemek.
* **Dosya:** `backend/app/tools/turning_point_and_cycle_detector.py`
* **Matematiksel Algoritma:** Bry-Boschan yerel ekstrema tespiti + CUSUM rejim kırılımı.
* **Grafik:** **Zirve/Dip İşaretli Döngü & Rejim Gölgelendirme Grafiği**
  - *Ana Çizgi:* Zaman serisi trendi.
  - *▲ Yeşil Üçgen:* Tespit edilen zirveler (Peaks).
  - *▼ Kırmızı Ters Üçgen:* Tespit edilen dipler (Troughs).
  - *Arka Plan Gölgeleri:* Kırmızı gölge (Daralma Döngüsü), Yeşil gölge (Genişleme/Toparlanma Döngüsü).
* **Girdi & Çıktı:**
  ```python
  class Input(BaseModel):
      series_id: str = Field(description="Seri ID'si")
      dimension: str | None = None
      metric: str = "value"
      smoothing_window: int = 3
      min_cycle_length: int = 4
      start_date: str | None = None
      end_date: str | None = None
  ```
  - Çıktıda: `peaks`, `troughs`, `current_phase`, `duration_months`, `max_drawdown_pct`, `chart_url`.

---

## 4. Geliştirme ve Entegrasyon Adımları

1. **Bağımlılık Kurulumu:**
   - `matplotlib` paketinin eklenmesi (`requirements.txt` ve sanal ortama kurulum).
2. **Görselleştirici Modülü ([`chart_generator.py`](file:///c:/Projects/kkb/backend/app/services/chart_generator.py)):**
   - `generate_deflator_chart()`, `generate_elasticity_chart()`, `generate_concentration_chart()`, `generate_cycle_chart()` fonksiyonlarının yazılması.
3. **4 Aracın Geliştirilmesi:**
   - `real_value_deflator.py`, `elasticity_and_sensitivity_analyzer.py`, `risk_concentration_analyzer.py`, `turning_point_and_cycle_detector.py`.
4. **Araçların Kaydı ([`__init__.py`](file:///c:/Projects/kkb/backend/app/tools/__init__.py) & [`loop.py`](file:///c:/Projects/kkb/backend/app/agent/loop.py)):**
   - `AVAILABLE_TOOLS` havuzuna dahil edilmesi.
5. **Prompt ve UI Entegrasyonu ([`system_prompt.md`](file:///c:/Projects/kkb/backend/app/prompts/system_prompt.md)):**
   - Modele, araçlardan dönen `chart_url` bilgisini nihai yanıtta markdown görseli `![Grafik](chart_url)` olarak gömmesi kuralının verilmesi.
6. **Kapsamlı Test Süiti:**
   - 4 tool için matematiksel ve grafik üretim testlerinin yazılması (`tests/tools/test_*.py`).

---

## 5. Doğrulama Planı

| Test | Kapsam | Beklenen Sonuç |
|---|---|---|
| **Deflator & Chart** | Kredi Serisi vs TÜFE | Reel daralma hesaplanmalı ve `static/charts/deflator_*.png` üretilmeli |
| **Elasticity & Chart** | Faiz vs Konut Kredisi | Negatif elastikiyet ve regresyon scatter grafiği üretilmeli |
| **Concentration & Chart** | FinTÜRK İl Bazlı NPL | CR3/CR5, HHI skoru ve Pareto bar grafiği üretilmeli |
| **Cycle Detector & Chart** | Konut Satış Serisi | Tepe/dip noktaları tespit edilip yeşil/kırmızı işaretli grafik üretilmeli |
| **Full Pytest Suite** | Tüm sistem testleri | 273+ testin tamamının hatasız geçmesi |
