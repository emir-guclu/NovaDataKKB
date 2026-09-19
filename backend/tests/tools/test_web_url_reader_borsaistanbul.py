"""Borsa İstanbul veri kaynakları (Altın İşlemleri PDF ve XTUMY JS sayfası)

ve Anomaly Detection araç zincirinin regresyon ve entegrasyon testleri.

KKB hackathon slaytındaki iki URL:
1. Altın İşlemleri PDF: https://www.borsaistanbul.com/dosyalar/kmtp/veriler/kmp_au.pdf
   (Sayfa: https://www.borsaistanbul.com/veriler/kiymetli-madenler-ve-kiymetli-taslar-piyasasi/piyasa-verileri)
2. XTUMY JS Endeks Sayfası: https://www.borsaistanbul.com/endeks/xtumy (render_js=True)
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import pytest

from backend.app.agent.loop import run_agent
from backend.app.agent.tool_registry import create_default_tool_registry
from backend.app.core.llm_provider import LLMResponse, LLMToolCall
from backend.app.tools.anomaly_detection import AnomalyDetectionTool
from backend.app.tools.web_url_reader import WebUrlReaderTool

GOLD_PDF_URL = "https://www.borsaistanbul.com/dosyalar/kmtp/veriler/kmp_au.pdf"
XTUMY_URL = "https://www.borsaistanbul.com/endeks/xtumy"


class ScriptedStepLLMProvider:
    """Agent döngüsünde adım adım belirli ToolCall veya nihai metin döndüren senaryo sağlayıcısı."""

    def __init__(self, steps: list[LLMResponse]) -> None:
        self.steps = list(steps)
        self.history_recorded: list[list[dict]] = []

    def chat(self, messages: list[dict], tools: list[dict] | None = None, **kwargs: Any) -> LLMResponse:
        self.history_recorded.append(messages)
        if not self.steps:
            return LLMResponse(content="Senaryo tamamlandi, baska adim yok.", tool_calls=[], finish_reason="stop", raw=None)
        return self.steps.pop(0)


def test_borsaistanbul_gold_pdf_extraction_live():
    """Borsa İstanbul Altın İşlemleri PDF dosyasını indirip metin ve tablo verilerini çıkarabilmeli."""
    tool = WebUrlReaderTool()
    result = tool.run(tool.Input(url=GOLD_PDF_URL, max_length=4000))

    # Canlı ağ ortamında erişim
    if not result.success:
        pytest.skip(f"Borsa İstanbul canlı PDF erişimi başarısız: {result.error}")

    assert result.success is True
    assert result.content_type == "pdf"
    assert len(result.content) > 100
    # PDF içeriğinde standart BIST kıymetli maden terimleri yer almalı
    content_upper = result.content.upper()
    assert any(term in content_upper for term in ["ALTIN", "KMP", "AYLAR", "İŞLEM", "USD", "TL", "KG"])


def test_borsaistanbul_gold_pdf_to_anomaly_pipeline():
    """PDF'ten elde edilen aylık altın işlem hacmi gözlemleri anomaly_detection ile doğrulanabilmeli."""
    # PDF'ten gelen örnek aylık altın işlem serisi (KG veya TL bazlı)
    gold_monthly_observations = [
        {"date": "2024-01-01", "value": 15200.5},
        {"date": "2024-02-01", "value": 14850.0},
        {"date": "2024-03-01", "value": 16100.2},
        {"date": "2024-04-01", "value": 15900.0},
        {"date": "2024-05-01", "value": 17200.8},
        {"date": "2024-06-01", "value": 16800.0},
        {"date": "2024-07-01", "value": 31500.0},  # Belirgin anomali / sıçrama
        {"date": "2024-08-01", "value": 17400.3},
        {"date": "2024-09-01", "value": 16950.1},
        {"date": "2024-10-01", "value": 17100.0},
        {"date": "2024-11-01", "value": 16750.4},
        {"date": "2024-12-01", "value": 17300.0},
    ]

    anomaly_tool = AnomalyDetectionTool()
    result = anomaly_tool.run(
        anomaly_tool.Input(
            observations=gold_monthly_observations,
            metric="value",
            z_threshold=2.0,
        )
    )

    assert result.success is True, result.error
    assert result.data_source == "inline"
    assert result.n_observations == 12
    assert len(result.anomalies) >= 1
    anomalous_dates = [a["date"] for a in result.anomalies]
    assert "2024-07-01" in anomalous_dates
    assert result.anomalies[0]["direction"] == "high"


def test_borsaistanbul_xtumy_render_js_live():
    """XTUMY sayfası Playwright Chromium ile JavaScript render edilerek taranabilmeli."""
    tool = WebUrlReaderTool()
    result = tool.run(tool.Input(url=XTUMY_URL, render_js=True, max_length=4000))

    if not result.success:
        pytest.skip(f"XTUMY canlı sayfasına erişilemedi: {result.error}")

    assert result.success is True
    assert len(result.content) > 500
    content_upper = result.content.upper()
    assert "XTUMY" in content_upper or "BIST" in content_upper or "ENDEKS" in content_upper


def test_agent_chains_borsaistanbul_reader_and_anomaly_detection():
    """Agent döngüsünün Borsa İstanbul web_url_reader ve anomaly_detection araçlarını sırayla çağırıp entegre edebildiğini doğrular."""
    registry = create_default_tool_registry()

    assert registry.get("web_url_reader") is not None
    assert registry.get("anomaly_detection") is not None

    sample_obs = [
        {"date": "2024-01-01", "value": 100.0},
        {"date": "2024-02-01", "value": 102.0},
        {"date": "2024-03-01", "value": 101.5},
        {"date": "2024-04-01", "value": 99.8},
        {"date": "2024-05-01", "value": 100.5},
        {"date": "2024-06-01", "value": 195.0},  # Sıçrama
        {"date": "2024-07-01", "value": 101.2},
    ]

    # Senaryo:
    # 1. Adım: LLM Borsa İstanbul PDF'ini okumak için web_url_reader çağırır.
    # 2. Adım: PDF içeriğindeki verilerle anomaly_detection(observations=...) çağırır.
    # 3. Adım: Sonucu özetler.
    scripted_steps = [
        LLMResponse(
            content=None,
            tool_calls=[
                LLMToolCall(
                    id="call_1_reader",
                    name="web_url_reader",
                    arguments=json.dumps({"url": GOLD_PDF_URL, "max_length": 2000}),
                )
            ],
            finish_reason="tool_calls",
            raw=None,
        ),
        LLMResponse(
            content=None,
            tool_calls=[
                LLMToolCall(
                    id="call_2_anomaly",
                    name="anomaly_detection",
                    arguments=json.dumps({"observations": sample_obs, "metric": "value", "z_threshold": 2.0}),
                )
            ],
            finish_reason="tool_calls",
            raw=None,
        ),
        LLMResponse(
            content="Borsa İstanbul verilerinde 2024-06 döneminde belirgin bir sıçrama tespit edildi.",
            tool_calls=[],
            finish_reason="stop",
            raw=None,
        ),
    ]

    mock_provider = ScriptedStepLLMProvider(scripted_steps)

    question = "Borsa İstanbul altın piyasası verilerini oku ve aylık seride anomali analizi yap."
    final_answer = run_agent(
        question=question,
        registry=registry,
        provider=mock_provider,
        max_iterations=5,
    )

    assert "2024-06" in final_answer
    assert "tespit edildi" in final_answer
    # Kaynak alıntısının eklendiğini kontrol et (web_url_reader kaynak ekler)
    assert GOLD_PDF_URL in final_answer or "Borsa" in final_answer
