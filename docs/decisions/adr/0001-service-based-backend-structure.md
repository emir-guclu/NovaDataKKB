# ADR-0001: Servis Bazlı Backend Kod Organizasyonu ve LLM Araçları Mimarisi

* **Durum:** ACCEPTED (KABUL EDİLDİ)
* **Tarih:** 2026-09-08
* **Karar Verenler:** Ekip Üyeleri / Mimar
* **Yerine Geçtiği:** —
* **Yerini Alan:** —

## 1. Bağlam ve Problem Tanımı
Backend kodunun modüler, sürdürülebilir, test edilebilir ve LLM ajanlarının araçları (tool-calling / agent tools) ile rahat entegre olabilecek bir yapıda kurgulanması gerekmektedir. Klasik katmanlı (layered - yatay `api/`, `services/`, `models/`) mimari ile servis/modül bazlı (dikey dilimler, `app/` altında toplanan domain modülleri ve izole `tools/`) mimari arasında yapılacak seçim; modül sınırlarını, kodun bakım maliyetini ve geliştirici hızını doğrudan etkilemektedir.

## 2. Karar
**Seçilen Seçenek:** Servis Bazlı Klasör Mimarisi (`app/` çekirdeği + `app/tools/` + `backend/` altyapısı).

Backend mimarisi servis bazlı klasör yapısı üzerine kurulacaktır:
* Tüm çekirdek uygulama bileşenleri, domain modülleri ve veri modelleri `app/` dizini altında toplanacaktır (`app/modules/`, `app/models/`, `app/core/`).
* LLM'lerin kullanabileceği tüm ajan fonksiyon ve araçları ayrılmış bir `app/tools/` klasöründe izole edilecektir.
* Veritabanı göç araçları (`alembic/`), dağıtım betikleri ve ortam yapılandırmaları ise `backend/` ana kök dizini altında konumlandırılacaktır.

### Değerlendirilen Seçenekler ve 5 Eksenli Karşılaştırma Matrisi

| Eksen | Seçenek 1: Klasik Yatay Katmanlı Mimari | Seçenek 2: Servis Bazlı Mimari (`app/` + `tools/`) [SEÇİLEN] | Seçenek 3: Bağımsız Mikroservisler |
|---|---|---|---|
| **Performans** | Standart monolit performansı | Doğrudan modül içi fonksiyon çağrısı, sıfır ağ gecikmesi | Servisler arası HTTP/gRPC gecikmesi (yüksek overhead) |
| **Karmaşıklık** | Düşük-Orta (özellikler yatay katmanlara dağılır) | Düşük-Orta (domain ve LLM tool sınırları net izole) | Çok yüksek (dağıtık sistem ve ağ yönetimi) |
| **Ölçeklenebilirlik** | Orta (büyüdükçe klasör içi dosya şişmesi) | Yüksek (yeni servis/modül veya LLM tool'u eklemek diğerlerini etkilemez) | Çok yüksek |
| **Sürdürülebilirlik** | Özellik güncellemelerinde birden fazla katmanı gezme zorluğu | Yüksek (domain bazlı modüler yapı ve açık tool sözleşmeleri) | Düşük (küçük ekip için operasyonel bakım yükü) |
| **Maliyet / Hız** | Başlangıçta hızlı, zamanla bakım maliyeti artar | Hızlı geliştirme, düşük bilişsel yük, dengeli bakım | Yüksek altyapı, dağıtım ve gözlemlenebilirlik maliyeti |

## 3. Gerekçe ve Belirleyici Faktör
* **Belirleyici Faktör:** LLM Entegrasyon İzolasyonu ve Modüler Domain Sınırları.
* **Açıklama:** Klasik katmanlı mimaride tek bir işlevsel domaini değiştirmek için çok sayıda yatay klasörde gezinmek gerekir ve LLM tool'ları genel servis kodları arasına karışarak sınır bulanıklığı yaratır. Servis bazlı yapıda her domain modülü kendi mantığını kapsüllerken, `app/tools/` klasörü LLM araçlarının tek bir merkezden, standart sözleşmelerle sunulmasını sağlar. `alembic` gibi altyapı araçlarının `backend/` seviyesinde tutulması ise çekirdek uygulama (`app/`) dizininin temiz kalmasını garanti eder.

## 4. Sonuçlar ve Riskler
* **Olumlu Sonuçlar:**
  * Modül sınırları ve sorumluluklar netleşir; ekip üyeleri birbirinin kodunu ezmeden paralel çalışabilir.
  * LLM araçları (`tools`) izole bir alanda tanımlandığı için model promptlarına/fonksiyon kayıtlarına kolayca bağlanabilir.
  * Altyapı (`alembic/`) uygulama mantığından ayrıştırılır.
* **Olumsuz Sonuçlar ve Riskler:**
  * Modüller arası kontrolsüz doğrudan referanslarda döngüsel bağımlılık (circular import) riski oluşabilir.
* **Azaltma Stratejisi:**
  * Paylaşılan veri modelleri ve genel yardımcılar `app/models/` veya `app/core/` altında merkezileştirilecek; modüller birbirleriyle doğrudan sıkı bağlı olmak yerine açık servis fonksiyonları üzerinden haberleşecektir.

## 5. Bağlayıcı Kurallar
* `* [T-0001-1] Backend iş mantığı ve çekirdek bileşenleri (modüller, modeller, LLM tool'ları) app/ dizini altında servis bazlı organize edilmelidir.`
* `* [T-0001-2] LLM ajanları tarafından çağrılabilir tüm araç ve fonksiyon tanımları app/tools/ klasörü altında izole edilmelidir.`
* `* [T-0001-3] Veritabanı migrasyonları (alembic) ve ortam yapılandırmaları doğrudan backend/ kök dizininde yer almalı, app/ içine karıştırılmamalıdır.`
