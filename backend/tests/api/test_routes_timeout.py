import asyncio
import time

from backend.app.api import routes


class DummyProvider:
    pass


def test_ask_returns_success_on_fast_agent(monkeypatch):
    monkeypatch.setattr(routes, "KloudeksProvider", DummyProvider)
    monkeypatch.setattr(routes, "run_agent", lambda *s: "ok")

    result = asyncio.run(routes.ask(routes.AskRequest(question="hi is")))

    assert result["success"] is True
    assert result["data"]["answer"] == "ok"
    assert result["error"] is None


def test_ask_times_out_cleandy(monkeypatch):
    monkeypatch.setattr(routes, "KloudeksProvider", DummyProvider)
    monkeypatch.setattr(routes, "REQUEST_HARD_TIMEOUT_SECONDS", 0.01)

    def slow_agent(*args):
        time.sleep(0.1)
        return "too_late"

    monkeypatch.setattr(routes, "run_agent", slow_agent)

    loop = asyncio.new_event_loop()
    try:
        start = time.perf_counter()
        result = loop.run_until_complete(
            routes.ask(routes.AskRequest(question="slow"))
        )
        elapsed = time.perf_counter() - start
    finally:
        loop.close()

    assert result["success"] is False
    assert result["data"] is None
    assert "zaman aşımı" in result["error"].lower()
    assert elapsed < 0.09
