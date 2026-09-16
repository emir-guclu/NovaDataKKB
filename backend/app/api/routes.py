from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend.app.agent.loop import run_agent
from backend.app.agent.tool_registry import create_default_tool_registry
from backend.app.core.llm_provider import (
    KloudeksProvider,
    get_available_providers,
    get_default_provider,
)


logger = logging.getLogger(__name__)

router = APIRouter()

REQUEST_HARD_TIMEOUT_SECONDS = float(os.getenv("REQUEST_HARD_TIMEOUT_SECONDS", "900"))
AGENT_MAX_ITERATIONS = int(os.getenv("AGENT_MAX_ITERATIONS", "12"))


class AskRequest(BaseModel):
    question: str
    history: list[dict[str, Any]] = Field(default_factory=list)
    provider: str | None = Field(default=None, description="deepseek, nvidia veya kloudeks")


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

        answer = await asyncio.wait_for(
            asyncio.to_thread(
                run_agent,
                request.question,
                registry,
                provider,
                AGENT_MAX_ITERATIONS,
                _collect,
                normalized_history,
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
            loop.call_soon_threadsafe(queue.put_nowait, slim)
        except Exception:
            pass

    async def gen():
        provider = _resolve_provider(request.provider)
        task = asyncio.create_task(asyncio.to_thread(
            run_agent, request.question, registry, provider,
            AGENT_MAX_ITERATIONS, on_event, normalized_history))
        while not task.done() or not queue.empty():
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
