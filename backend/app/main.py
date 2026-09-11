import os
import json
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

# Yeni kloudeks modülünden QwenChatClient içe aktarılıyor
from backend.app.modules.llm.kloudeks import QwenChatClient, KloudeksAPIError
from backend.app.modules.tools.agent_tools import web_search_tool, change_detection_tool

load_dotenv(os.path.join(os.path.dirname(__file__), "../../../.env"))

app = FastAPI(
    title="NOVA Analytics Agent API",
    description="KKB Hackathon için geliştirilen analitik ajan arka planı."
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class AskRequest(BaseModel):
    question: str

# Kloudeks API İstemcisini Başlat (Şifreyi .env'den otomatik alacak)
llm_client = QwenChatClient()

@app.get("/health")
def health_check():
    return {"status": "ok", "message": "NOVA Backend tıkır tıkır çalışıyor!"}

@app.post("/ask")
def ask_agent(request: AskRequest):
    question_lower = request.question.lower()
    context = ""
    
    # 1. Web Search Tool Entegrasyonu
    if any(word in question_lower for word in ["ara", "haber", "internette", "nedir", "kimdir", "son durum"]):
        search_results = web_search_tool(request.question)
        context += f"\n[Web Arama Sonuçları]:\n{search_results}\n"
        
    # 2. Change Detection Tool Entegrasyonu
    if any(word in question_lower for word in ["kırılma", "trend", "değişim", "anormallik", "analiz"]):
        # Şimdilik Lakehouse'u simüle eden örnek zaman serisi verisi gönderiyoruz
        dummy_data = [
            {"date": "2023-01", "value": 100}, {"date": "2023-02", "value": 105},
            {"date": "2023-03", "value": 102}, {"date": "2023-04", "value": 110},
            {"date": "2023-05", "value": 108}, {"date": "2023-06", "value": 180}, # Kırılma Noktası (Ani yükseliş)
            {"date": "2023-07", "value": 185}, {"date": "2023-08", "value": 190}
        ]
        detection_result = change_detection_tool(dummy_data, threshold=1.5)
        context += f"\n[Zaman Serisi Trend Analizi (Change Detection)]:\n{json.dumps(detection_result, ensure_ascii=False)}\n"
        
    system_prompt = "Sen 'NOVA' adında çok zeki ve ciddi bir finansal analiz ajanısın. KKB (Kredi Kayıt Bürosu) hackathon'u için geliştirildin. Kullanıcıya verilen ek bilgileri (Arama sonuçları veya Trend analizleri) kendi bilginmiş gibi harmanlayarak mantıklı ve profesyonel cevaplar ver."
    
    user_prompt = request.question
    if context:
        user_prompt += f"\n\n--- SİSTEM EK BİLGİLERİ ---\nAşağıdaki araç çıktılarını referans alarak cevap ver:{context}"
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]
    
    try:
        # LLM'i çağırıyoruz (O yazdığımız retry mekanizmalı client üzerinden)
        answer = llm_client.chat(messages=messages)
        
        return {
            "answer": answer,
            "evidence": ["EVDS: TP.KTF10", "BDDK: Aylık Kredi Hacmi"],
            "status": "success"
        }
    except Exception as e:
        return {
            "answer": f"⚠️ Kloudeks Yapay Zeka motoruna erişilemedi: {str(e)}",
            "status": "error"
        }
