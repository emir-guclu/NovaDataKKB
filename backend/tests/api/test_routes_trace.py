import asyncio

from backend.app.api import routes


class DummyProvider:
    pass


def test_ask_collects_tool_trace_from_on_event(monkeypatch):
    monkeypatch.setattr(routes, "KloudeksProvider", DummyProvider)

    def fake_run_agent(question, registry, provider, max_iterations, on_event, history):
        on_event("llm_decision", {"tool_name": "evds_data_service", "arguments": '{"action": "search"}'})
        on_event("tool_output", {"tool_name": "evds_data_service", "success": True, "tool_duration_s": 1.234})
        on_event("llm_decision", {"tool_name": "lakehouse_query", "arguments": '{"table": "gold_x"}'})
        on_event("tool_output", {"tool_name": "lakehouse_query", "success": False, "tool_duration_s": 0.5})
        return "nihai cevap"

    monkeypatch.setattr(routes, "run_agent", fake_run_agent)

    result = asyncio.run(routes.ask(routes.AskRequest(question="soru")))

    assert result["success"] is True
    assert result["answer"] == "nihai cevap"
    assert result["data"]["answer"] == "nihai cevap"
    assert result["error"] is None

    trace = result["data"]["trace"]
    assert trace == [
        {"type": "tool_call", "tool_name": "evds_data_service", "arguments": '{"action": "search"}'},
        {"type": "tool_result", "tool_name": "evds_data_service", "success": True, "duration_s": 1.23},
        {"type": "tool_call", "tool_name": "lakehouse_query", "arguments": '{"table": "gold_x"}'},
        {"type": "tool_result", "tool_name": "lakehouse_query", "success": False, "duration_s": 0.5},
    ]


def test_ask_succeeds_even_when_no_events_fire(monkeypatch):
    monkeypatch.setattr(routes, "KloudeksProvider", DummyProvider)
    monkeypatch.setattr(routes, "run_agent", lambda *args: "ok")

    result = asyncio.run(routes.ask(routes.AskRequest(question="soru")))

    assert result["success"] is True
    assert result["data"]["answer"] == "ok"
    assert result["data"]["trace"] == []
