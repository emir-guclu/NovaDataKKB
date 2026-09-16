from __future__ import annotations

import io
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from backend.app.api import routes
from backend.app.main import app


class DummyProvider:
    def ocr(self, image_base64: str) -> str:
        return "| Donem | TUFE |\n| 2024-01 | 64.8 |"


def test_upload_attachment_csv(tmp_path):
    with TestClient(app) as client:
        csv_content = b"Tarih,Enflasyon\n2024-01,64.8\n"
        response = client.post(
            "/api/v1/upload-attachment",
            files={"file": ("enflasyon.csv", io.BytesIO(csv_content), "text/csv")},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["filename"] == "enflasyon.csv"
    assert data["content_type"] == "csv"
    assert "| Tarih | Enflasyon |" in data["markdown_content"]
    assert "saved_path" in data


def test_upload_attachment_image(monkeypatch):
    monkeypatch.setattr(routes, "KloudeksProvider", DummyProvider)

    with patch("backend.app.services.attachment_parser.parse_image_ocr", return_value="| Donem | TUFE |\n| 2024-01 | 64.8 |"):
        with TestClient(app) as client:
            img_content = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
            response = client.post(
                "/api/v1/upload-attachment",
                files={"file": ("chart.png", io.BytesIO(img_content), "image/png")},
            )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["filename"] == "chart.png"
    assert data["content_type"] == "image"
    assert "TUFE" in data["markdown_content"]


def test_upload_attachment_unsupported_extension():
    with TestClient(app) as client:
        zip_content = b"PK\x03\x04..."
        response = client.post(
            "/api/v1/upload-attachment",
            files={"file": ("malicious.exe", io.BytesIO(zip_content), "application/octet-stream")},
        )

    assert response.status_code == 400 or (response.status_code == 200 and response.json()["success"] is False)
    data = response.json()
    assert data["success"] is False
    assert "Desteklenmeyen" in data["error"]


def test_upload_attachment_oversized():
    with TestClient(app) as client:
        huge_content = b"A" * (11 * 1024 * 1024)  # 11MB (>10MB limit)
        response = client.post(
            "/api/v1/upload-attachment",
            files={"file": ("huge.csv", io.BytesIO(huge_content), "text/csv")},
        )

    assert response.status_code in (400, 413) or (response.status_code == 200 and response.json()["success"] is False)
    data = response.json()
    assert data["success"] is False
    assert "10 MB" in data["error"] or "boyut" in data["error"].lower() or "sinir" in data["error"].lower()


def test_ask_endpoint_passes_attachment(monkeypatch):
    monkeypatch.setattr(routes, "KloudeksProvider", DummyProvider)

    called_args = {}

    def fake_run_agent(question, registry, provider, max_iterations, on_event, history, attachment_content=None, attachment_name=None):
        called_args["question"] = question
        called_args["attachment_content"] = attachment_content
        called_args["attachment_name"] = attachment_name
        return "Cevap"

    monkeypatch.setattr(routes, "run_agent", fake_run_agent)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/ask",
            json={
                "question": "Bu tablodaki veriyi yorumla",
                "attachment_content": "| A | B |\n| 1 | 2 |",
                "attachment_name": "tablo.csv",
            },
        )

    assert response.status_code == 200
    assert called_args["attachment_content"] == "| A | B |\n| 1 | 2 |"
    assert called_args["attachment_name"] == "tablo.csv"
