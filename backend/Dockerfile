# Build context repo kökü olmalıdır (docker-compose.yml içinde context: .) ki
# "backend" paketi backend.app.main:app olarak import edilebilsin ve
# backend/app/tools/lakehouse_query.py gibi dosyalardaki
# Path(__file__).resolve().parents[3] tabanlı PROJECT_ROOT hesaplamaları
# konteyner içinde de repo köküyle (/app) aynı sonucu versin.
FROM python:3.11.9-slim

WORKDIR /app

# --- Sistem bağımlılığı incelemesi (ÖN İŞ) ---
# requirements.txt içinde sistem paketi (ör. OCR için tesseract, PDF için poppler)
# gerektiren bir bağımlılık YOK: pypdf saf Python'dır, OCR
# backend/app/services/url_content_extractor.py içinde yerel tesseract değil,
# KloudeksProvider.ocr() üzerinden uzak bir LLM çağrısıyla yapılıyor.
# url_content_extractor.py'deki tarayıcı fallback'i (`_fetch_with_browser`)
# `playwright.sync_api` kullanıyor, ANCAK bu import try/except ImportError ile
# opsiyonel bırakılmış ve playwright requirements.txt'te YOK — yani bilinçli
# olarak devre dışı bırakılmış bir "yumuşak" bağımlılık. Bu yüzden burada da
# playwright/chromium kurulmuyor (kurulsaydı ek apt paketleri + ~300MB chromium
# gerekirdi); eksikliğinde kod zaten "Playwright kurulu degil" uyarısıyla
# statik HTML'e düşüyor.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend ./backend

EXPOSE 8000

CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
