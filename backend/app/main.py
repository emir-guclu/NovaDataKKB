import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.routes import router

load_dotenv(Path(__file__).resolve().parents[2] / ".env")


def get_allowed_origins() -> list[str]:
    origins = ["http://localhost:3000"]
    frontend_origin = os.getenv("FRONTEND_ORIGIN", "").strip()
    if frontend_origin and frontend_origin not in origins:
        origins.append(frontend_origin)
    return origins


app = FastAPI(
    title="NOVA Analytics Agent API",
    description="KKB Hackathon için geliştirilen analitik ajan arka planı.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_allowed_origins(),
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/health")
def health_check():
    return {"status": "ok", "message": "NOVA Backend çalışıyor."}


app.include_router(router)
