# Deploy Hedefi Karşılaştırma Analizi (Deploy Target Comparison)

Bu doküman, **Faz A — Madde 1** kapsamında ekibin deploy hedefi (VPS vs PaaS vs Serverless) kararını hızlı ve veri odaklı verebilmesi için hazırlanmıştır. Karar ekibe aittir; bu doküman riskleri, kısıtları ve önerileri sunar.

---

## 1. Mimari Gereksinimler ve Kritik Kısıtlar

NovaData KKB asistanı yalnızca standart bir CRUD API değildir; aşağıdaki özelliklere sahiptir:

1. **Çok Adımlı Agent Döngüsü (`max_iterations=6`):**
   - Kullanıcı sorusu → LLM → Tool 1 (Katalog/DuckDB) → LLM → Tool 2 (EVDS / Web scraping) → LLM → Nihai Yanıt.
   - Ortalama yanıt süresi 5–15 saniye arasında olsa da, web içeriği okuma, PDF/OCR veya karmaşık analitik hesaplamalarda **30–60 saniyeye** kadar uzayabilir.
2. **DuckDB Dosya Kalıcılığı (Local Persistence):**
   - Sistem `data/lakehouse.duckdb`, `data/silver/silver.duckdb` ve `data/aligned/monthly/aligned.duckdb` yerel dosyalarına doğrudan bağlanır (read-only veya analytical query).
   - Dosya boyutu onlarca/yüzlerce MB olabilir.
3. **Kloudeks/MIA API Bağlantısı (`https://mia.csp.kloudeks.com/v1`):**
   - Kurumsal LLM gateway bağlantısı. Olası IP kısıtı/whitelist politikaları ve rate-limit backoff süreleri (2s, 4s, 8s bekleme döngüsü).

---

## 2. Platform Karşılaştırma Tablosu

| Kriter | Kendi VPS'imiz (Hetzner / DO / EC2) | PaaS / Container (Railway / Render) | Serverless (Vercel / Netlify / AWS Lambda) |
| :--- | :--- | :--- | :--- |
| **Timeout Esnekliği** | **Sınırsız** (FastAPI / Uvicorn üzerinde istenilen timeout ayarlanabilir) | **Yüksek** (Background worker veya 100–300s web timeout; Railway'de timeout kısıtı esnektir) | **Kritik Risk** (Vercel Free: 10–15s; Pro: 60s limit. Çok adımlı agent döngüsü timeout'a takılır) |
| **Yerel Disk / DuckDB** | **Kalıcı (Persistent NVMe)**. DuckDB dosyaları doğrudan yerel diskte çalışır. | **Persistent Volume** eklenebilir veya Docker image içine gömülebilir. | **Geçici (Ephemeral)**. Dosyalar her çağrıda silinir veya read-only Lambda katmanına sıkıştırılmalıdır. |
| **IP Whitelist / Sabit IP** | **Sabit Statik IP (Tek IP)**. Kloudeks veya harici servisler IP whitelist isterse sıfır sürtünme. | Genellikle değişken IP havuzu (Sabit IP için ek egress proxy veya özel add-on gerekir). | Değişken binlerce IP havuzu. IP kısıtında çalışmaz (NAT Gateway gerektirir). |
| **Kurulum Süresi** | ~1-2 saat (Docker compose, Nginx, SSL certbot kurulumu). | **~15-30 dakika** (Git push ile otomatik Docker build). | ~30-45 dakika (Serverless adapter ayarları, DuckDB C-extension uyumu gerektirir). |
| **Maliyet** | **~5 - 10 € / ay** (Hetzner 4 vCPU, 8 GB RAM; sabit maliyet). | **~5 - 15 $ / ay** (Kullanıma göre veya başlangıç planı). | Ücretsiz tier var, fakat ek süre ve bellek aşımlarında maliyet hızla artar. |
| **Operasyonel Yük** | Orta (Linux güncellemesi, Docker yönetimi, log rotasyonu). | **Düşük** (Otomatik CI/CD, yönetilen altyapı). | Düşük (ancak cold start ve binary dependency debugging zordur). |

---

## 3. Risk Değerlendirmesi

### Risk A: Serverless Timeout Riski (Vercel vb.)
- Agent birden fazla ardışık tool çağırdığında (örneğin önce `series_catalog_search`, ardından `lakehouse_query`, yetersizse `web_search`), toplam latency 15 saniyeyi kolayca aşar.
- Vercel ücretsiz tier'ında 10-15 saniyede fonksiyon zorla sonlandırılır (`FUNCTION_INVOCATION_TIMEOUT`). Kullanıcı yarıda kalmış yanıt alır.

### Risk B: DuckDB & C-Extension Uyumluluğu
- DuckDB C++ binary tabanlıdır. Serverless ortamlarda Linux glibc sürümü ve dosya kilitleme (read-only connection lock) sorunları çıkabilir. Docker ortamında ise %100 öngörülebilirdir.

### Risk C: Kloudeks Egress IP Kısıtı
- Kloudeks/MIA kurumsal bir ortamda çalıştığı için değişken sunucusuz IP havuzlarından gelen isteklerde rate-limit veya güvenlik kısıtlamalarına takılma riski taşır. VPS'te tek ve sabit bir IP ile izin listesine girmek kolaydır.

---

## 4. Ekibe Tavsiye ve Önerilen Yol Haritası

### **Öneri (Tavsiye Edilen Seçenek):**
1. **Demo ve Kısa Vade (Hızlı Çözüm): Railway / Render (Docker Tabanlı PaaS)**
   - Mevcut Dockerfile veya `requirements.txt` ile doğrudan ayağa kaldırılabilir.
   - 15 dakikada yayına alınır, SSL ve domain otomatik sağlanır.
   - Timeout 100-300 saniyeye ayarlanabilir.
2. **Üretim ve Nihai Hedef (En Güvenli & Ekonomik Çözüm): Kendi VPS'imiz (Ubuntu + Docker Compose)**
   - Hem frontend hem backend tek bir 5-7 €'luk VPS üzerinde (Hetzner Cloud CX22/CX32) çalıştırılabilir.
   - DuckDB yerel diskte en yüksek IOPS performansıyla çalışır.
   - Kloudeks için sabit statik IP sağlar.
   - Sıfır timeout kısıtı.

### **Kesinlikle Kaçınılması Gereken:**
- **Vercel / AWS Lambda (Serverless Backend):** DuckDB kalıcılığı ve agent döngüsünün 10-15 saniyelik timeout sınırlarına takılması nedeniyle demo gününde yüksek hata riski oluşturur.
