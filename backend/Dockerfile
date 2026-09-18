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
# playwright requirements.txt'te kurulu; url_content_extractor.py'deki dinamik
# sayfa render'ı (render_js) için chromium ve sistem bağımlılıkları gerekiyor.
COPY requirements.txt pytest.ini ./
RUN pip install --no-cache-dir -r requirements.txt
RUN playwright install --with-deps chromium

COPY backend ./backend

EXPOSE 8000

CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
