from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from backend.app.services.url_content_extractor import extract_url_content
from backend.app.tools.base import BaseTool

logger = logging.getLogger(__name__)


class WebUrlReaderTool(BaseTool):
    name = "web_url_reader"
    description = (
        "Verilen web URL'sindeki HTML, CSV/Excel, PDF veya gorsel icerigi indirip "
        "metne donusturur. Kullanici belirli bir URL'deki icerigi analiz etmeni "
        "istediginde kullan."
    )

    class Input(BaseModel):
        url: str = Field(description="Okunacak http veya https URL")
        max_length: int = Field(
            default=4000,
            le=20000,
            description="Dondurulecek metnin maksimum karakter uzunlugu",
        )

    class Output(BaseModel):
        success: bool
        url: str
        content_type: str | None = None
        title: str | None = None
        content: str = ""
        error: str | None = None

    def run(self, params: Input) -> Output:
        try:
            extracted = extract_url_content(params.url)
            content = extracted.text[: params.max_length] if extracted.success else ""
            return self.Output(
                success=extracted.success,
                url=params.url,
                content_type=extracted.content_type,
                title=extracted.title,
                content=content,
                error=extracted.error,
            )
        except Exception as exc:
            logger.exception("web_url_reader failed")
            return self.Output(
                success=False,
                url=params.url,
                content_type=None,
                content="",
                error=str(exc),
            )
