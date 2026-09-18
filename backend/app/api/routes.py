from __future__ import annotations

import asyncio
from datetime import datetime
import json
import logging
import os
from pathlib import Path
from typing import Any
import uuid

from fastapi import APIRouter, File, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from backend.app.agent.loop import run_agent
from backend.app.agent.tool_registry import create_default_tool_registry
from backend.app.core.llm_provider import (
    KloudeksProvider,
    get_available_providers,
    get_default_provider,
)
from backend.app.services.attachment_parser import parse_uploaded_file


logger = logging.getLogger(__name__)

router = APIRouter()

REQUEST_HARD_TIMEOUT_SECONDS = float(os.getenv("REQUEST_HARD_TIMEOUT_SECONDS", "900"))
AGENT_MAX_ITERATIONS = int(os.getenv("AGENT_MAX_ITERATIONS", "12"))
MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB
ALLOWED_EXTENSIONS = {".xlsx", ".xls", ".csv", ".pdf", ".png", ".jpg", ".jpeg", ".webp"}
PROJECT_ROOT = Path(__file__).resolve().parents[3]
UPLOAD_DIR = PROJECT_ROOT / "data" / "uploads"


class AskRequest(BaseModel):
    question: str
    history: list[dict[str, Any]] = Field(default_factory=list)
    provider: str | None = Field(default=None, description="deepseek, nvidia veya kloudeks")
    attachment_content: str | None = Field(default=None, description="Ekli dosya/görselin Markdown ayrıştırılmış içeriği")
    attachment_name: str | None = Field(default=None, description="Ekli dosya/görselin orijinal adı")


registry = create_default_tool_registry()


def _resolve_provider(requested_provider: str | None = None):
    if requested_provider:
        return get_default_provider(requested_provider)
    from backend.app.core.llm_provider import KloudeksProvider as RealKloudeksProvider
    if KloudeksProvider is not RealKloudeksProvider:
        return KloudeksProvider()
    return get_default_provider()


@router.get("/api/v1/providers")
@router.get("/providers")
async def list_providers():
    """Mevcut LLM saglayicilarini ve durumlarini dondurur."""
    return {"providers": get_available_providers()}


@router.post("/api/v1/upload-attachment")
@router.post("/upload-attachment")
async def upload_attachment(file: UploadFile = File(...)):
    """Kullanıcının yüklediği görsel, Excel, CSV veya PDF dosyasını kaydeder ve ayrıştırır."""
    original_filename = file.filename or "uploaded_file"
    suffix = Path(original_filename).suffix.lower()

    if suffix not in ALLOWED_EXTENSIONS:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": f"Desteklenmeyen dosya türü: '{suffix}'. İzin verilen formatlar: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
            },
        )

    try:
        content = await file.read()
        if len(content) > MAX_UPLOAD_BYTES:
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "error": f"Dosya boyutu 10 MB sınırını aşıyor ({len(content) / (1024 * 1024):.1f} MB).",
                },
            )

        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = f"{timestamp}_{uuid.uuid4().hex[:8]}_{Path(original_filename).name}"
        saved_path = UPLOAD_DIR / safe_name
        saved_path.write_bytes(content)

        # Yalnızca görsel yüklemelerinde LLM / OCR provider'ı çöz
        provider = None
        if suffix in {".png", ".jpg", ".jpeg", ".webp"}:
            provider = _resolve_provider()

        parsed = await asyncio.to_thread(
            parse_uploaded_file,
            saved_path,
            original_filename,
            provider,
        )

        if not parsed.get("success"):
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "error": parsed.get("error", "Dosya ayrıştırılamadı."),
                    "filename": original_filename,
                },
            )

        return {
            "success": True,
            "filename": original_filename,
            "saved_path": str(saved_path),
            "content_type": parsed.get("content_type"),
            "markdown_content": parsed.get("markdown_content"),
            "metadata": parsed.get("metadata", {}),
        }
    except Exception as exc:
        logger.exception("Dosya yukleme veya ayristirma sirasinda hata")
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": f"Dosya işlenirken sunucu hatası oluştu: {str(exc)}",
            },
        )


@router.post("/api/v1/ask")
@router.post("/ask")
async def ask(request: AskRequest):
    try:
        provider = _resolve_provider(request.provider)
        normalized_history = [
            {"role": ("assistant" if t.get("role") == "agent" else t.get("role")),
             "content": t.get("content")}
            for t in request.history
            if isinstance(t, dict)
        ]

        trace: list[dict] = []

        def _collect(event_type: str, payload: dict) -> None:
            try:
                if event_type == "llm_decision":
                    trace.append({
                        "type": "tool_call",
                        "tool_name": payload.get("tool_name"),
                        "arguments": payload.get("arguments"),
                    })
                elif event_type == "tool_output":
                    trace.append({
                        "type": "tool_result",
                        "tool_name": payload.get("tool_name"),
                        "success": payload.get("success"),
                        "duration_s": round(float(payload.get("tool_duration_s") or 0), 2),
                    })
            except Exception:
                logger.warning("trace toplama hatasi", exc_info=True)

        agent_kwargs = {}
        if request.attachment_content:
            agent_kwargs["attachment_content"] = request.attachment_content
        if request.attachment_name:
            agent_kwargs["attachment_name"] = request.attachment_name

        answer = await asyncio.wait_for(
            asyncio.to_thread(
                run_agent,
                request.question,
                registry,
                provider,
                AGENT_MAX_ITERATIONS,
                _collect,
                normalized_history,
                **agent_kwargs,
            ),
            timeout=REQUEST_HARD_TIMEOUT_SECONDS,
        )
        return {
            "success": True,
            "answer": answer,
            "data": {"answer": answer, "trace": trace},
            "error": None,
        }
    except asyncio.TimeoutError:
        logger.warning("Request timeout: %s", request.question[:100])
        return {
            "success": False,
            "data": None,
            "error": "İstek zaman aşımına uğradı, lütfen tekrar deneyin veya soruyu sadeleştirin.",
        }
    except Exception as exc:
        logger.exception("Agent loop failed")
        return {
            "success": False,
            "data": None,
            "error": str(exc),
        }


@router.post("/api/v1/ask/stream")
async def ask_stream(request: AskRequest):
    normalized_history = [
        {"role": ("assistant" if t.get("role") == "agent" else t.get("role")),
         "content": t.get("content")}
        for t in request.history
        if isinstance(t, dict)
    ]

    queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def on_event(kind: str, payload: dict) -> None:
        try:
            # llm_input olayı tüm mesaj geçmişini taşır — ASLA olduğu gibi
            # yayınlama, yalnızca seçilmiş/özet alanları istemciye gönder.
            slim = {
                "kind": kind,
                "tool_name": payload.get("tool_name"),
                "iteration": payload.get("iteration"),
                "success": payload.get("success"),
                "duration_s": payload.get("tool_duration_s"),
            }
            if kind == "llm_decision":
                slim["arguments"] = payload.get("arguments")
            loop.call_soon_threadsafe(queue.put_nowait, slim)
        except Exception:
            pass

    async def gen():
        provider = _resolve_provider(request.provider)
        agent_kwargs = {}
        if request.attachment_content:
            agent_kwargs["attachment_content"] = request.attachment_content
        if request.attachment_name:
            agent_kwargs["attachment_name"] = request.attachment_name

        task = asyncio.create_task(asyncio.to_thread(
            run_agent, request.question, registry, provider,
            AGENT_MAX_ITERATIONS, on_event, normalized_history,
            **agent_kwargs))
        deadline = loop.time() + REQUEST_HARD_TIMEOUT_SECONDS

        while not task.done() or not queue.empty():
            if loop.time() > deadline:
                # to_thread altındaki thread iptal edilemez; amaç thread'i durdurmak değil,
                # istemciye hata döndürüp sonsuz keepalive akışını bitirmek.
                task.cancel()
                logger.warning("Stream timeout: %s", request.question[:100])
                yield f"data: {json.dumps({'kind': 'error', 'error': 'İstek zaman aşımına uğradı, lütfen tekrar deneyin veya soruyu sadeleştirin.'}, ensure_ascii=False)}\n\n"
                return
            try:
                evt = await asyncio.wait_for(queue.get(), timeout=0.5)
                yield f"data: {json.dumps(evt, ensure_ascii=False)}\n\n"
            except asyncio.TimeoutError:
                yield ": keepalive\n\n"
        try:
            answer = task.result()
            yield f"data: {json.dumps({'kind': 'done', 'answer': answer}, ensure_ascii=False)}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'kind': 'error', 'error': str(exc)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream",
                              headers={"Cache-Control": "no-cache",
                                       "X-Accel-Buffering": "no"})
