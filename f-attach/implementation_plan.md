# f-attach: Dinamik Dosya ve Görsel Ekleme, Ayrıştırma (OCR / Excel / PDF) ve Prompt Enjeksiyonu Planı

Bu plan, kullanıcının/jürinin demo anında sağlayabileceği harici finansal veri dosyalarını (`.xlsx`, `.xls`, `.csv`, `.pdf`) ve **ekran görüntüsü / tablo görsellerini (`.png`, `.jpg`, `.jpeg`, `.webp`)** güvenle yüklemesini, backend'de zaman damgalı depolanıp OCR / Tablo ayrıştırıcı ile temiz metne/tabloya dönüştürülmesini ve DuckDB şemasını bozmadan doğrudan **güvenli prompt bağlamı (`<attached_document>`)** olarak ajana iletilmesini sağlar.

---

## 🎯 Mimari Tasarım ve Akış

```
[Frontend (Arayüz)]
  ├── 📎 Ataş / Dosya & Görsel Seçici (.xlsx, .csv, .pdf, .png, .jpg, .jpeg, .webp)
  └── 📊 Seçilen Dosya/Görsel Rozeti (Önizleme/İsim, Boyut, Kaldır butonu)
           │
           ▼ (Dosya Gönderimi: POST /api/v1/upload-attachment)
[Backend Depolama & Parser Motoru]
  ├── 1. Zaman Damgalı Depolama: data/uploads/{YYYYMMDD_HHMMSS}_{uuid}_{filename}
  ├── 2. Akıllı Ayrıştırma (attachment_parser.py):
  │       ├── 📸 Görseller (.png, .jpg, .jpeg, .webp) -> OCR / Vision Modeli (Qwen-VL / Llama-Vision)
  │       │       └── Ekran görüntüsü veya taranmış rapordan metin ve tablo çıkarma
  │       ├── 📊 Excel (.xlsx, .xls) -> Sayfa tarama, başlık tespiti, Markdown Tablosu
  │       ├── 📄 CSV (.csv) -> Ayraç tespiti (virgül, noktalı virgül, tab), Markdown Tablosu
  │       └── 📑 PDF (.pdf) -> Sayfalar, tablolar ve finansal özetler
  └── 3. Yapılandırılmış Markdown Çıktısı Üretimi
           │
           ▼
[Ajan Prompt Enjeksiyonu (loop.py & sanitizer.py)]
  ├── Kullanıcı Sorusu + Güvenli XML Bloğu:
  │   <attached_document filename="faiz_tablosu_screenshot.png" type="image_ocr">
  │   | Ay | Politika Faizi | Konut Kredisi Faizi |
  │   | 2024-01 | %45.0 | %42.5 |
  │   </attached_document>
  └── Ajan, görselden/tablodan çıkarılan bu veriyi okur ve EVDS/BDDK Lakehouse toolları ile anında çaprazlar!
```

---

## 📋 Önerilen Değişiklikler

### 1. Backend: Depolama, Parser ve OCR Katmanı

#### [NEW] [attachment_parser.py](file:///c:/Projects/kkb/backend/app/services/attachment_parser.py)
- **Fonksiyonlar:**
  - `parse_image_ocr(file_path: Path, provider: LLMProvider | None = None) -> str`: Görseli base64'e çevirir, `provider.ocr(...)` (Qwen-VL / Llama-Vision) üzerinden çağırarak görseldeki metin ve tabloları Markdown formatına döker.
  - `parse_excel(file_path: Path) -> str`: Çoklu sayfaları (sheets) okur, her sayfayı Markdown tablosuna dönüştürür.
  - `parse_csv(file_path: Path) -> str`: Dinamik ayraç tespiti (`csv.Sniffer` / pandas) ile tabloyu çıkarır.
  - `parse_pdf(file_path: Path) -> str`: PDF sayfalarındaki tabloları ve sayısal özetleri metne döker.
  - `parse_uploaded_file(file_path: Path, original_filename: str) -> dict`: Dosya/görsel uzantısına göre uygun motoru (OCR veya Parser) çalıştırır, satır/sütun sayısını ve Markdown formatlı tabloyu döner.

#### [MODIFY] [routes.py](file:///c:/Projects/kkb/backend/app/api/routes.py)
- `POST /api/v1/upload-attachment` endpoint'i:
  - `UploadFile` kabul eder.
  - `data/uploads/` altında zaman damgasıyla kaydeder.
  - `parse_uploaded_file` ile parse edip dosya/görsel metaverisi + Markdown içeriğini döndürür.
- `AskRequest` modeline opsiyonel `attachment_content: str | None` ve `attachment_name: str | None` alanları eklenecek.

#### [MODIFY] [sanitizer.py](file:///c:/Projects/kkb/backend/app/prompts/sanitizer.py) & [loop.py](file:///c:/Projects/kkb/backend/app/agent/loop.py)
- Ekteki veri/OCR içeriğini `<attached_document>` güvenli bloğuna saracak ve prompt injection filtresinden geçirecek yardımcı fonksiyon.

---

### 2. Frontend: Dosya ve Görsel Yükleme Deneyimi

#### [MODIFY] [page.tsx](file:///c:/Projects/kkb/frontend/app/[locale]/page.tsx)
- **Giriş Alanına (Input) Ataş Butonu (📎):**
  - Dosya ve Görsel seçici (`input type="file" accept=".xlsx,.xls,.csv,.pdf,.png,.jpg,.jpeg,.webp"`).
- **Ekli Dosya / Görsel Rozeti (Attachment Chip):**
  - Seçilen dosyanın türüne göre ikon (📸 Görsel, 📊 Excel, 📄 Belge), dosya adı, boyutu ve kaldırma butonu (`✕`).
- **Gönderim Akışı:**
  - Mesaj gönderildiğinde dosya/görsel backend'e yüklenip OCR/Parse edilecek, ardından dönen tablo içeriği `history`/`ask` payload'ına iliştirilecek.

#### [MODIFY] [tr.json](file:///c:/Projects/kkb/frontend/messages/tr.json) & [en.json](file:///c:/Projects/kkb/frontend/messages/en.json)
- Dosya ve görsel yükleme etiketleri (`attach_file`, `file_uploaded`, `file_remove`, `unsupported_file`, `ocr_processing`).

---

## 🛡️ Güvenlik ve Kararlılık Kriterleri

1. **DuckDB İzolasyonu:** Yüklenen rastgele veriler veya OCR metinleri DuckDB şemasına yazılmaz; veritabanı bozulma riski %0'dır.
2. **Prompt Injection Koruması:** Yüklenen dosya veya görsel içindeki gizli yönergeler `sanitizer.py` tarafından taranır.
3. **Boyut Limiti:** Maksimum 10 MB dosya boyutu kontrolü uygulanır.

---

## 🧪 Doğrulama Planı

### Otomatik Testler
- `backend/tests/services/test_attachment_parser.py`:
  - Örnek Görsel (OCR), Excel, CSV ve PDF dosyalarının doğru Markdown çıktısına dönüştüğünün testi.
- `backend/tests/api/test_upload_attachment.py`:
  - Upload endpoint'inin dosya ve görsel kaydetme ve parse yanıtı testi.
- Tüm test süitinin çalıştırılması:
  ```powershell
  cmd /c "set PYTHONPATH=backend;. && .venv\Scripts\pytest backend/tests"
  ```

### Manuel Doğrulama
1. Tarayıcıdan bir finansal tablo ekran görüntüsü (`.png`) seçilecek.
2. "Bu görseldeki verileri TCMB EVDS faiz oranlarıyla karşılaştır" sorusu sorulacak.
3. OCR modelinin görseldeki sayıları başarıyla okuyup, EVDS verileriyle çaprazlayarak yanıt ürettiği doğrulanacak.
