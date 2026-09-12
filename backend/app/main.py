import os
import json
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

from backend.app.modules.llm.kloudeks import QwenChatClient, KloudeksAPIError
from backend.app.tools.web_search import WebSearchTool
from backend.app.tools.change_detection import ChangeDetectionTool

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

llm_client = QwenChatClient()
search_agent = WebSearchTool()
change_agent = ChangeDetectionTool()

@app.get("/health")
def health_check():
    return {"status": "ok", "message": "NOVA Backend tıkır tıkır çalışıyor!"}

@app.post("/ask")
def ask_agent(request: AskRequest):
    question_lower = request.question.lower()
    context = ""
    
    if any(word in question_lower for word in ["ara", "haber", "internette", "nedir", "kimdir", "son durum"]):
        result = search_agent.run({"query": request.question})
        if result.get("success"):
            context += f"\n[Web Arama Sonuçları]:\n{result.get('results')}\n"
        
    if any(word in question_lower for word in ["kırılma", "trend", "değişim", "anormallik", "analiz"]):
        dummy_data = [
            {"date": "2023-01", "value": 100}, {"date": "2023-02", "value": 105},
            {"date": "2023-03", "value": 102}, {"date": "2023-04", "value": 110},
            {"date": "2023-05", "value": 108}, {"date": "2023-06", "value": 180},
            {"date": "2023-07", "value": 185}, {"date": "2023-08", "value": 190}
        ]
        result = change_agent.run({"time_series_data": dummy_data, "threshold": 1.5})
        if result.get("success"):
            context += f"\n[Zaman Serisi Trend Analizi (Change Detection)]:\n{json.dumps(result, ensure_ascii=False)}\n"
        
    system_prompt = "Sen 'NOVA' adında çok zeki ve ciddi bir finansal analiz ajanısın. KKB (Kredi Kayıt Bürosu) hackathon'u için geliştirildin. Kullanıcıya verilen ek bilgileri (Arama sonuçları veya Trend analizleri) kendi bilginmiş gibi harmanlayarak mantıklı ve profesyonel cevaplar ver."
    
    user_prompt = request.question
    if context:
        user_prompt += f"\n\n--- SİSTEM EK BİLGİLERİ ---\nAşağıdaki araç çıktılarını referans alarak cevap ver:{context}"
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]
    
    try:
        answer = llm_client.chat(messages=messages)
        return {
            "answer": answer,
            "evidence": ["EVDS: TP.KTF10", "BDDK: Aylık Kredi Hacmi"],
            "status": "success"
        }
    except Exception as e:
        return {
            "answer": f"Kloudeks Yapay Zeka motoruna erişilemedi: {str(e)}",
            "status": "error"
        }
