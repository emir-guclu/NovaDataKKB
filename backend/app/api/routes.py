from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from backend.app.agent.loop import run_agent
from backend.app.agent.tool_registry import create_default_tool_registry
from backend.app.core.llm_provider import KloudeksProvider


router = APIRouter()


class AskRequest(BaseModel):
    question: str


registry = create_default_tool_registry()


@router.post("/api/v1/ask")
def ask(request: AskRequest):
    try:
        provider = KloudeksProvider()
        answer = run_agent(request.question, registry, provider)
        return {
            "success": True,
            "data": {"answer": answer},
            "error": None,
        }
    except Exception as exc:
        return {
            "success": False,
            "data": None,
            "error": str(exc),
        }
