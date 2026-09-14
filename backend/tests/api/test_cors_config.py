import os

from backend.app.main import get_allowed_origins


def test_cors_origins_default_to_localhost(monkeypatch):
    monkeypatch.delenv("FRONTEND_ORIGIN", raising=False)

    origins = get_allowed_origins()

    assert "http://localhost:3000" in origins
    assert "*" not in origins


def test_cors_origins_include_frontend_origin(monkeypatch):
    monkeypatch.setenv("FRONTEND_ORIGIN", "https://frontend.example.com")

    origins = get_allowed_origins()

    assert "https://frontend.example.com" in origins
    assert "http://localhost:3000" in origins
    assert "*" not in origins
