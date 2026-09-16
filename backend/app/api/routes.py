from __future__ import annotations

import asyncio
import logging
import os

from fastapi import APIRouter
from pydantic import BaseModel

from backend.app.agent.loop import run_agent
from backend.app.agent.tool_registry import create_default_tool_registry
from backend.app.core.llm_provider import KloudeksProvider


logger = logging.getLogger(__name__)

router = APIRouter()

REQUEST_HARD_TIMEOUT_SECONDS = float(os.getenv("REQUEST_HARD_TIMEOUT_SECONDS", "100"))


class AskRequest(BaseModel):
    question: str


registry = create_default_tool_registry()


@router.post("/api/v1/ask")
@router.post("/ask")
async def ask(request: AskRequest):
    try:
        provider = KloudeksProvider()
        answer = await asyncio.wait_for(
            asyncio.to_thread(
                run_agent,
                request.question,
                registry,
                provider,
            ),
            timeout=REQUEST_HARD_TIMEOUT_SECONDS,
        )
        return {
            "success": True,
            "answer": answer,
            "data": {"answer": answer},
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
