# ADR-0002: EVDS Veri Erişimi ve Kütüphane Seçimi

* **Durum:** ACCEPTED (KABUL EDİLDİ)
* **Tarih:** 2026-09-08
* **Karar Verenler:** Ekip Üyeleri / Mimar
* **Yerine Geçtiği:** —
* **Yerini Alan:** —

## 1. Bağlam ve Problem Tanımı
TCMB Elektronik Veri Dağıtım Sistemi (EVDS) üzerinden 2021–2026 makroekonomik serilerinin (faiz, TÜFE, konut fiyat endeksi, döviz kurları vb.) çekilmesi ve Bronze katmanı için kaynaktan gelen ham formatta arşivlenmesi gerekmektedir. EVDS veri erişimi için toplulukta yaygın kullanılan açık kaynaklı bir kütüphane (`evds`), daha genişletilmiş CLI/önbellek odaklı bir paket (`evdspy`) veya projeye özel asenkron bir HTTP istemcisi (`httpx`) arasında seçim yapılması; geliştirme hızı, bakım yükü, çoklu API anahtarı rotasyonu ve Lakehouse Bronze katmanı uyumluluğu açısından kritik bir karardır.

## 2. Karar
**Seçilen Seçenek:** `evds` pip paketi (Fatih Erol / erolf) ve etrafında hafif bir servis sarmalayıcısı (wrapper).

TCMB EVDS veri erişimi için mevcut sanal ortamda (`.venv`) kurulu olan resmi olmayan topluluk standardı `evds` (v0.4.0) paketi kullanılacaktır. Bronze katmanı için ham veri çekimi `raw=True` parametresiyle JSON formatında yapılacak; API rate-limit ve hata yönetimi `.env` üzerindeki anahtar havuzunu (`EVDS_API_KEY_1..4`) yöneten `backend/app/modules/evds/` altındaki servis katmanında çözülecektir.

### Değerlendirilen Seçenekler ve 5 Eksenli Karşılaştırma Matrisi

| Eksen | Seçenek 1: `evds` pip paketi [SEÇİLEN] | Seçenek 2: Özel `httpx` İstemcisi (Custom Client) | Seçenek 3: `evdspy` pip paketi |
|---|---|---|---|
| **Performans** | Standart senkron HTTP (`requests`), IO-bound işlemler için yeterli | Yüksek asenkron (`httpx.AsyncClient`) eşzamanlı çekim | Standart senkron HTTP, dosya tabanlı dahili önbellek |
| **Karmaşıklık** | Çok düşük (yalın Python sınıfı, sıfır yapılandırma yükü) | Orta (özel retry, backoff, session ve endpoint modelleri yazımı) | Yüksek (CLI, menü yapılandırması ve diskte ayar dosyaları tutma) |
| **Ölçeklenebilirlik** | Orta (çoklu anahtar rotasyonuna izin verir, hafif bellek ayak izi) | Yüksek (tamamen asenkron ve mikroservis uyumlu) | Düşük-Orta (statik konfigürasyon bağımlılığı, dinamik multi-key zorluğu) |
| **Sürdürülebilirlik** | Yüksek (minimal kod, `raw=True` ile ham API yanıtına sıfır müdahale) | Yüksek (tam kod hakimiyeti, sıfır dış kütüphane bağımlılığı) | Düşük (büyük soyutlama katmanı, headless/backend ortamında pürüzler) |
| **Maliyet / Hız** | Anında kullanıma hazır, sıfır geliştirme maliyeti, maksimum hız | 1-2 gün özel istemci geliştirme ve test eforu | Öğrenme eğrisi ve CLI/ayar yapısını temizleme eforu |

## 3. Gerekçe ve Belirleyici Faktör
* **Belirleyici Faktör:** Geliştirme Hızı, Sadelik ve Bronze Katmanı İçin Doğrudan Ham JSON (`raw=True`) Desteği.
* **Açıklama:** 13 günlük kısıtlı geliştirme takviminde sıfırdan özel bir HTTP istemcisi yazmak zaman kaybı yaratacaktır. `evdspy` ise CLI ve interaktif menü özellikleri nedeniyle backend API ve otonom pipeline içine gereksiz dosya/durum karmaşıklığı sokmaktadır. `evds` paketi ise doğrudan `raw=True` parametresi ile TCMB'den dönen saf JSON verisini hiçbir kayba uğratmadan vermekte, `.env` dosyamızdaki 4 farklı API anahtarı arasında döngü kurmamıza izin vermekte ve projede halihazırda test edilmiş olarak bulunmaktadır.

## 4. Sonuçlar ve Riskler
* **Olumlu Sonuçlar:**
  * Dakikalar içinde veri çekmeye başlanabilir; `F-001` teslimatı hızlanır.
  * `raw=True` ile kaynaktan gelen veriler değiştirilmeden `data/bronze/evds/` altına JSON olarak arşivlenir (Lakehouse Bronze prensibi).
  * Çoklu API anahtarı havuzu (`EVDS_API_KEY_1..4`) ile istekler dinamik olarak anahtarlar arasında paylaştırılabilir.
* **Olumsuz Sonuçlar ve Riskler:**
  * Kütüphane varsayılan olarak senkron (`requests`) çalıştığı için çok sayıda seriyi paralel çekerken thread havuzu (`ThreadPoolExecutor`) gerekir.
  * Kütüphanenin kendi içinde yerleşik exponential backoff / retry mekanizması bulunmamaktadır.
* **Azaltma Stratejisi:**
  * `backend/app/modules/evds/client.py` içerisinde `evdsAPI` sınıfı sarmalanarak (wrapper pattern) HTTP 429 veya bağlantı hatalarında otomatik olarak havuzdaki diğer anahtara geçen güvenli bir servis yazılacaktır.

## 5. Bağlayıcı Kurallar
* `* [T-0002-1] EVDS veri erişimi için evds pip paketi kullanılmalıdır.`
* `* [T-0002-2] Bronze katmanı arşivlemesinde evds kütüphanesi veri çekim çağrıları raw=True parametresiyle ham JSON döndürecek şekilde yapılmalıdır.`
* `* [T-0002-3] EVDS API isteklerinde .env üzerinden sağlanan çoklu anahtar havuzu (EVDS_API_KEY_1..4) kullanılarak rotasyon ve hata yönetimi sağlanmalıdır.`
