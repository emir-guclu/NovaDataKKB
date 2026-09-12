# F-web_agent v2: Web URL Reader & Multimodal Parser İyileştirme Planı

## 1. Problem Tanımı ve Gözlemler

`test_dynamic_tools.py` üzerindeki canlı senaryolarda `WebUrlReaderTool` ve `url_content_extractor` servisinin gerçek dünya koşullarındaki davranışları incelendi ve şu 4 darboğaz tespit edildi:

1. **HTML Link Kaybı (Altın İşlemleri PDF):**
   - Sayfada `<a href="/dosyalar/kmtp/veriler/kmp_au.pdf">Altın İşlemleri</a>` bağlantısı bulunmasına rağmen `BeautifulSoup.get_text()` kullanıldığı için link uçtu; LLM yalnızca metni gördü. Linki göremeyen LLM tahmini bir URL uydurdu ve sunucu **404** döndü.
2. **JavaScript Dinamik İçerik (BIST XTUMY):**
   - Modern SPA veya JS tabanlı sayfalarda ham HTML yalnızca boş bir iskelet barındırıyor. Rakamlar istemci tarafında yüklendiği için `requests.get()` ile veri boş geldi.
3. **WAF ve Bot Engeli (Excel 403 Forbidden):**
   - Serviste kullanılan `USER_AGENT = "NOVA-Analytics-Agent/1.0"` başlığı, Cloudflare veya benzeri WAF sistemleri tarafından bot olarak algılanıp engellendi.
4. **Çoklu Ortam (HTML + Görsel/Şema) Sayfalar (`/bistech-teknolojisi`):**
   - Sayfa hem metin hem de kritik bir teknoloji mimarisi görseli (`teknoloji_gorsel.jpeg`) içeriyor. Mevcut sistem sadece metni aldı, sayfadaki şemaları yok saydı.

---

## 2. Mimari Çözüm (Hibrit Pipeline)

```mermaid
flowchart TD
    A["Kullanıcı / Agent URL İsteği"] --> B["1. Aşama: Hızlı İstek (requests + Browser Headers)"]
    B -->|Başarılı 200| C{"İçerik Türü?"}
    B -->|403 Bot Engeli veya Boş JS İskeleti| D["2. Aşama: Dinamik Fallback (Playwright)"]
    D --> C
    
    C -->|PDF / Excel / CSV| E["Formatına Göre Parser (pypdf, pandas, openpyxl)"]
    C -->|Görsel (png, jpg, webp)| F["OCR / VLM Motoru (KloudeksProvider.ocr)"]
    C -->|HTML Sayfası| G["Zengin HTML Ayrıştırıcı (_extract_html_v2)"]
    
    G --> H["1. Sayfa Metni (Markdown Formatı)"]
    G --> I["2. Bulunan Ek Dökümanlar (.pdf, .xlsx, .csv) -> Mutlak URL"]
    G --> J["3. Sayfa İçi Görseller ve Şemalar (img alt + src) -> Mutlak URL"]
    
    H & I & J --> K["LLM Sentezi ve Çift Kademeli İnceleme"]
    K -->|Kullanıcı Detay Şema veya Rapor İstediyse| L["Agent 2. Adımda Doğrudan İlgili Görsel veya PDF URL'sini Çağırır"]
```

---

## 3. Yapılacak Değişiklikler

### A. `backend/app/services/url_content_extractor.py`

1. **Modern Tarayıcı Başlıkları (Headers):**
   - `User-Agent`: Modern Chrome masaüstü kimliği (`Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36`).
   - `Accept`: `text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,application/pdf,*/*;q=0.8`.
   - `Accept-Language`: `tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7`.
2. **Zengin HTML Parser (`_extract_html_v2`):**
   - Göreceli linkleri `urllib.parse.urljoin(base_url, href)` ile tam mutlak linke dönüştürme.
   - Sayfadaki döküman linklerini (`.pdf`, `.xlsx`, `.csv`, `.docx`) tespit edip `Bulunan Dosyalar` bloğuna ekleme.
   - Sayfadaki anlamlı `<img>` etiketlerini tespit edip `Sayfa İçi Görseller / Şemalar` bloğuna ekleme.
3. **Playwright Dinamik Fallback Modülü (`_fetch_with_browser`):**
   - `playwright` kütüphanesi opsiyonel olarak kontrol edilecek.
   - Eğer sayfa JS ile yüklenen boş bir konteyner barındırıyorsa (`<div id="root"></div>`, `<div id="app"></div>` veya `< 300` karakter boş metin) veya `403` dönerse, Playwright headless Chromium devreye girerek render edilmiş HTML'i alacak.
   - Playwright kurulu değilse graceful şekilde statik HTML çıktısı ve net bir bilgilendirme sunulacak.

### B. LLM & Agent Loop Kural Güncellemesi

1. **Halüsinasyon Engeli:**
   - Sisteme açık kural: *"Sayfada açıkça listelenmeyen hiçbir URL'yi tahmin ederek uydurma. Sayfadaki 'Bulunan Dosyalar' veya 'Görseller' listesindeki gerçek URL'leri kullan."*
2. **Çift Kademeli İnceleme Yeteneği:**
   - HTML okunduktan sonra dönen ek döküman veya görsel URL'leri LLM'in dikkatine sunulacak; kullanıcı özel bir tablo/şema sorguluyorsa ajan ikinci iterasyonda doğrudan o URL'yi okuyacak.

---

## 4. Doğrulama ve Test Planı

1. **Senaryo 6.1 (PDF):** `https://www.borsaistanbul.com/veriler/kiymetli-madenler-ve-kiymetli-taslar-piyasasi/piyasa-verileri`
   - Sayfa okunduğunda `kmp_au.pdf` bağlantısının tespit edildiği ve ajanın o linki kullanarak PDF içeriğini (fiyat, hacim) okuduğu doğrulanacak.
2. **Senaryo 6.2 (HTML):** `https://www.borsaistanbul.com/bistech-teknolojisi`
   - Hem sayfa metninin hem de `teknoloji_gorsel.jpeg` görselinin başarıyla ayrıştırıldığı test edilecek.
3. **Senaryo 6.3 (Excel):**
   - Tarayıcı başlıklarıyla 403 hatasının aşıldığı veya açık bir public test Excel'i ile satır/sütun özetinin üretildiği teyit edilecek.
4. **Senaryo 6.4 (Görsel OCR):**
   - `https://www.borsaistanbul.com/file/inline-images/teknoloji_gorsel.jpeg` görselinin doğrudan OCR / VLM ile okunabildiği doğrulanacak.
