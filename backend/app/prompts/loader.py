from __future__ import annotations

from datetime import date
from pathlib import Path

SYSTEM_PROMPT_PATH = Path(__file__).resolve().parent / "system_prompt.md"


def get_system_prompt(today: str | None = None) -> str:
    """system_prompt.md dosyasını yükler ve dinamik değişkenleri (tarih vb.) enjekte eder."""
    today_str = today or date.today().isoformat()
    template = SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
    return template.format(today=today_str).strip()
