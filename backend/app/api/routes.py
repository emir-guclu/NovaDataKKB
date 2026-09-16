from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from backend.app.agent.loop import run_agent
from backend.app.agent.tool_registry import create_default_tool_registry
from backend.app.core.llm_provider import KloudeksProvider


logger = logging.getLogger(__name__)

router = APIRouter()

REQUEST_HARD_TIMEOUT_SECONDS = float(os.getenv("REQUEST_HARD_TIMEOUT_SECONDS", "900"))
AGENT_MAX_ITERATIONS = int(os.getenv("AGENT_MAX_ITERATIONS", "12"))


class AskRequest(BaseModel):
    question: str
    history: list[dict[str, Any]] = Field(default_factory=list)


registry = create_default_tool_registry()


@router.post("/api/v1/ask")
@router.post("/ask")
async def ask(request: AskRequest):
    try:
        provider = KloudeksProvider()
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
