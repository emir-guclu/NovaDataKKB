import app.core.llm_provider as provider_module
from app.core.llm_provider import KloudeksProvider


class FakeRateLimitError(Exception):
    pass


def test_rate_limit_retries_with_exponential_backoff(monkeypatch):
    monkeypatch.setattr(provider_module, "RateLimitError", FakeRateLimitError)

    sleeps = []
    provider = KloudeksProvider(
        api_key="test-key",
        client=object(),
        sleep_fn=sleeps.append,
    )

    attempts = {"count": 0}

    def operation():
        attempts["count"] += 1
        if attempts["count"] <= 3:
            raise FakeRateLimitError("429")
        return "ok"

    result = provider._with_rate_limit_retry(operation)

    assert result == "ok"
    assert attempts["count"] == 4
    assert sleeps == [2, 4, 8]
