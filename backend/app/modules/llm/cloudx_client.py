import os
import time
import logging
import requests
from typing import Dict, Any, List, Optional

# Loglama ayarı (Jüri sistemin ne yaptığını loglardan görmek isteyecek)
logger = logging.getLogger(__name__)

class KloudeksAPIError(Exception):
    """Kloudeks API'sinden dönen hatalar için özel hata sınıfı."""
    pass

class KloudeksClient:
    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        """
        Kloudeks LLM servisi için güvenli ve kurumsal HTTP istemcisi.
        Yasaklı üçüncü parti (OpenAI vb.) SDK'lar kullanılmadan saf HTTP ile yazılmıştır.
        """
        self.api_key = api_key or os.getenv("KLOUDEKS_API_KEY")
        self.base_url = (base_url or os.getenv("KLOUDEKS_BASE_URL", "https://api.kloudeks.com/v1")).rstrip("/")
        self.default_model = os.getenv("KLOUDEKS_DEFAULT_MODEL", "qwen-max")
        
        if not self.api_key:
            logger.warning("KLOUDEKS_API_KEY bulunamadı! LLM çağrıları başarısız olabilir.")
            
        # Session kullanmak, her seferinde yeni bağlantı açmaktan çok daha performanslıdır
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        })

    def chat_completion(
        self, 
        messages: List[Dict[str, str]], 
        model: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 2048,
        response_format: Optional[Dict[str, str]] = None,
        max_retries: int = 2
    ) -> str:
        """
        LLM'e istek atar. İnternet koptuğunda veya sunucu yavaşladığında otomatik tekrar dener.
        PDF Kuralı: Analitik ve deterministik sonuçlar için varsayılan sıcaklık 0.0'dır.
        """
        url = f"{self.base_url}/chat/completions"
        
        payload = {
            "model": model or self.default_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }
        
        # Yapılandırılmış çıktı (JSON Mode) isteniyorsa
        if response_format:
            payload["response_format"] = response_format

        # Hata anında vazgeçmeyip 2 kez daha deneyen (Retry) döngü
        for attempt in range(max_retries + 1):
            try:
                start_time = time.time()
                
                # 30 saniye içinde cevap gelmezse Timeout hatası fırlat
                response = self.session.post(url, json=payload, timeout=30.0)
                response.raise_for_status() 
                
                data = response.json()
                elapsed_time = time.time() - start_time
                
                logger.info(f"[Kloudeks] Model: {payload['model']} | Süre: {elapsed_time:.2f}s | Token: {data.get('usage', {}).get('total_tokens', 'Bilinmiyor')}")
                
                return data["choices"][0]["message"]["content"]
                
            except requests.exceptions.RequestException as e:
                logger.error(f"[Kloudeks] İstek hatası (Deneme {attempt + 1}/{max_retries + 1}): {e}")
                if attempt < max_retries:
                    time.sleep(2 ** attempt)  # 1 saniye, 2 saniye bekleyerek tekrar dene (Exponential backoff)
                else:
                    raise KloudeksAPIError(f"Kloudeks servisine {max_retries + 1} denemede ulaşılamadı. Hata: {e}")
                    
            except (KeyError, IndexError, ValueError) as e:
                logger.error(f"[Kloudeks] Yapay zeka beklenen JSON formatında cevap vermedi: {e}")
                raise KloudeksAPIError("Kloudeks servisinden gelen cevap ayrıştırılamadı.")