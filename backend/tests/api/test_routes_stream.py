from __future__ import annotations

import json
import time

from fastapi.testclient import TestClient

from backend.app.api import routes
from backend.app.main import app


class DummyProvider:
    pass


def _parse_sse_events(raw_text: str) -> list[dict]:
    events = []
    for chunk in raw_text.split("\n\n"):
        chunk = chunk.strip()
        if not chunk or not chunk.startswith("data: "):
            continue
        events.append(json.loads(chunk[len("data: "):]))
    return events


def test_ask_stream_emits_sse_events_ending_in_done(monkeypatch):
    monkeypatch.setattr(routes, "KloudeksProvider", DummyProvider)

    def fake_run_agent(question, registry, provider, max_iterations, on_event, history):
        on_event("llm_decision", {"tool_name": "series_catalog_search", "iteration": 1})
        on_event("tool_output", {"tool_name": "series_catalog_search", "success": True, "tool_duration_s": 1.2})
        return "nihai cevap"

    monkeypatch.setattr(routes, "run_agent", fake_run_agent)

    with TestClient(app) as client:
        response = client.post("/api/v1/ask/stream", json={"question": "test"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")

    raw_lines = [line for line in response.text.split("\n\n") if line.strip()]
    for line in raw_lines:
        assert line.startswith("data: ") or line.startswith(": keepalive")

    events = _parse_sse_events(response.text)
    assert len(events) >= 3

    assert events[0]["kind"] == "llm_decision"
    assert events[0]["tool_name"] == "series_catalog_search"

    assert events[1]["kind"] == "tool_output"
    assert events[1]["success"] is True
    assert events[1]["duration_s"] == 1.2

    assert events[-1]["kind"] == "done"
    assert events[-1]["answer"] == "nihai cevap"


def test_ask_stream_does_not_leak_full_message_history(monkeypatch):
    monkeypatch.setattr(routes, "KloudeksProvider", DummyProvider)

    def fake_run_agent(question, registry, provider, max_iterations, on_event, history):
        on_event(
            "llm_input",
            {
                "iteration": 1,
                "question": question,
                "messages": [{"role": "system", "content": "gizli sistem promptu " * 50}],
                "tools": ["cok-uzun-tool-listesi"],
            },
        )
        return "cevap"

    monkeypatch.setattr(routes, "run_agent", fake_run_agent)

    with TestClient(app) as client:
        response = client.post("/api/v1/ask/stream", json={"question": "test"})

    events = _parse_sse_events(response.text)
    llm_input_events = [e for e in events if e["kind"] == "llm_input"]
    assert len(llm_input_events) == 1
    assert "messages" not in llm_input_events[0]
    assert "tools" not in llm_input_events[0]
    assert "question" not in llm_input_events[0]


def test_ask_stream_with_zero_timeout_does_not_emit_timeout(monkeypatch):
    monkeypatch.setattr(routes, "KloudeksProvider", DummyProvider)
    monkeypatch.setattr(routes, "REQUEST_HARD_TIMEOUT_SECONDS", 0)

    def slow_run_agent(question, registry, provider, max_iterations, on_event, history):
        time.sleep(0.05)
        return "gec de olsa cevap"

    monkeypatch.setattr(routes, "run_agent", slow_run_agent)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/ask/stream",
            json={"question": "uzun analiz"},
        )

    events = _parse_sse_events(response.text)

    assert not any(event.get("kind") == "error" for event in events)
    assert events[-1]["kind"] == "done"
    assert events[-1]["answer"] == "gec de olsa cevap"
