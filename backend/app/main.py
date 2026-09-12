import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.routes import router

load_dotenv(os.path.join(os.path.dirname(__file__), "../../../.env"))

app = FastAPI(
    title="NOVA Analytics Agent API",
    description="KKB Hackathon için geliştirilen analitik ajan arka planı.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health_check():
    return {"status": "ok", "message": "NOVA Backend çalışıyor."}


app.include_router(router)
