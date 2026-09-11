import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

# Env dosyasını yükle
load_dotenv(os.path.join(os.path.dirname(__file__), "../../../.env"))

# Bizim yazdığımız o özel HTTP LLM istemcisi
from backend.app.modules.llm.cloudx_client import KloudeksClient

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
llm_client = KloudeksClient()

@app.get("/health")
def health_check():
    return {"status": "ok", "message": "NOVA Backend tıkır tıkır çalışıyor!"}

@app.post("/ask")
def ask_agent(request: AskRequest):
    # LLM'e gidecek sistem promptu
    system_prompt = "Sen 'NOVA' adında çok zeki ve ciddi bir finansal analiz ajanısın. KKB (Kredi Kayıt Bürosu) hackathon'u için geliştirildin. Kullanıcı sana veri sorduğunda kısa, profesyonel ve analitik cevaplar ver."
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": request.question}
    ]
    
    try:
        # LLM'i çağırıyoruz (O yazdığımız retry mekanizmalı client üzerinden)
        answer = llm_client.chat_completion(messages=messages)
        
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
