import asyncio
import json

from backend.app.api import routes


class DummyProvider:
    pass


def _fake_run_agent(question, registry, provider, max_iterations, on_event, history):
    on_event("llm_decision", {"tool_name": "change_detection", "arguments": '{"series_id": "x"}'})
    on_event(
        "tool_output",
        {
            "tool_name": "change_detection",
            "success": True,
            "tool_duration_s": 0.4,
            "result": '{"success": true, "rows": [{"value": 1250.5, "mom_pct_change": 3.27}]}',
        },
    )
    on_event(
        "tool_output",
        {"tool_name": "web_search", "success": False, "tool_duration_s": 0.1, "result": '{"value": 777}'},
    )
    return "Değer 1.250,5 milyon TL, aylık artış %3,27; ancak 999.999 uydurma."


def test_ask_includes_grounding_and_keeps_existing_fields(monkeypatch):
    monkeypatch.setattr(routes, "KloudeksProvider", DummyProvider)
    monkeypatch.setattr(routes, "run_agent", _fake_run_agent)

    result = asyncio.run(routes.ask(routes.AskRequest(question="soru")))

    assert result["success"] is True
    assert result["error"] is None
    assert result["answer"].startswith("Değer 1.250,5")
    assert result["data"]["answer"] == result["answer"]
    assert [t["type"] for t in result["data"]["trace"]] == ["tool_call", "tool_result", "tool_result"]

    grounding = result["data"]["grounding"]
    assert grounding["checked"] == 3
    assert grounding["grounded"] == 2
    assert grounding["ungrounded"] == ["999.999"]
    assert grounding["ratio"] == 2 / 3


def test_ask_trace_does_not_leak_raw_tool_results(monkeypatch):
    monkeypatch.setattr(routes, "KloudeksProvider", DummyProvider)
    monkeypatch.setattr(routes, "run_agent", _fake_run_agent)

    result = asyncio.run(routes.ask(routes.AskRequest(question="soru")))

    assert "1250.5" not in json.dumps(result["data"]["trace"])
    assert all("result" not in item for item in result["data"]["trace"])


def test_failed_tool_outputs_are_not_used_as_grounding_evidence(monkeypatch):
    monkeypatch.setattr(routes, "KloudeksProvider", DummyProvider)

    def run_agent(question, registry, provider, max_iterations, on_event, history):
        on_event("tool_output", {"tool_name": "t", "success": False, "tool_duration_s": 0, "result": '{"v": 345.6}'})
        return "Değer 345,6."

    monkeypatch.setattr(routes, "run_agent", run_agent)
    result = asyncio.run(routes.ask(routes.AskRequest(question="soru")))

    assert result["data"]["grounding"]["ungrounded"] == ["345,6"]


def test_grounding_failure_does_not_break_the_request(monkeypatch):
    monkeypatch.setattr(routes, "KloudeksProvider", DummyProvider)
    monkeypatch.setattr(routes, "run_agent", lambda *args: "cevap 345,6")

    def boom(answer, tool_outputs):
        raise RuntimeError("grounding patladı")

    monkeypatch.setattr(routes, "check_grounding", boom)
    result = asyncio.run(routes.ask(routes.AskRequest(question="soru")))

    assert result["success"] is True
    assert result["answer"] == "cevap 345,6"
    assert result["data"]["grounding"] is None


def test_stream_done_event_carries_grounding_and_slim_events_stay_slim(monkeypatch):
    monkeypatch.setattr(routes, "KloudeksProvider", DummyProvider)
    monkeypatch.setattr(routes, "run_agent", _fake_run_agent)

    async def collect():
        response = await routes.ask_stream(routes.AskRequest(question="soru"))
        chunks = []
        async for chunk in response.body_iterator:
            chunks.append(chunk if isinstance(chunk, str) else chunk.decode())
        return chunks

    events = [
        json.loads(line[len("data: "):])
        for chunk in asyncio.run(collect())
        for line in chunk.splitlines()
        if line.startswith("data: ")
    ]

    assert all("result" not in evt for evt in events)
    done = events[-1]
    assert done["kind"] == "done"
    assert done["answer"].startswith("Değer 1.250,5")
    assert done["grounding"]["checked"] == 3
    assert done["grounding"]["ungrounded"] == ["999.999"]
