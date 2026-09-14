from datetime import date
from pathlib import Path

from backend.app.prompts.loader import get_system_prompt, SYSTEM_PROMPT_PATH


def test_system_prompt_file_exists():
    assert SYSTEM_PROMPT_PATH.exists()
    assert SYSTEM_PROMPT_PATH.suffix == ".md"


def test_get_system_prompt_injects_today_and_contains_rules():
    custom_date = "2026-10-15"
    prompt = get_system_prompt(today=custom_date)

    assert custom_date in prompt
    assert "KKB'nin (Kredi Kayıt Bürosu) finansal veri analiz asistanısın" in prompt
    assert "BDDK, EVDS, FinTürk" in prompt
    assert "hava durumu, genel sohbet, kod yazma" in prompt
    assert "web_search tool'unu kullanabilirsin" in prompt
    assert "URL tahmin ederek uydurma" in prompt
    assert "evds_data_service" in prompt


def test_get_system_prompt_default_today():
    prompt = get_system_prompt()
    assert date.today().isoformat() in prompt
