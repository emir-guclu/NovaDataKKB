from __future__ import annotations

import json
import logging
import re
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from backend.app.core.llm_provider import LLMProvider, get_default_provider
from backend.app.tools.base import BaseTool

logger = logging.getLogger(__name__)


_CONNECTOR_RE = re.compile(
    r"\b(?:ile|ve|veya|arasindaki|arasindaki|arasındaki|arasında|arasinda|"
    r"karsilastir|karşılaştır|incele|baginti|bağıntı|iliski|ilişki|etki|"
    r"korelasyon|nedensellik|trend|analiz|yilinda|yılında|yili|yılı)\b",
    flags=re.IGNORECASE,
)


class SubTask(BaseModel):
    step: int = Field(..., description="Adim numarasi (1, 2, 3...)")
    objective: str = Field(..., description="Bu adimda cozulmesi gereken alt problem")
    focus_query: str = Field(
        ...,
        description="Katalog veya web aramasi icin optimize edilmis kisa aday sorgu",
    )
    expected_output: str = Field(..., description="Bu adimdan beklenen veri, seri veya bulgu")
    constraints: list[str] = Field(default_factory=list)
    date_range: str | None = None
    frequency_hint: str | None = None
    analysis_type: str | None = None


class AnalysisPlannerTool(BaseTool):
    name = "analysis_planner"
    description = (
        "Cok adimli, cok serili veya cok kaynakli veri analiz sorularini alt gorevlere, "
        "kisa focus_query arama ifadelerine ve sentez yonlendirmesine ayirir. Basit tekil "
        "seri aramalari icin kullanma; onlar once series_catalog_search ile aranmalidir."
    )

    class Input(BaseModel):
        complex_query: str = Field(
            ...,
            description=(
                "Ayrisitirilacak cok adimli, cok kaynakli, cok gostergeli veya "
                "karsilastirmali kullanici sorusu."
            ),
        )
        context_hint: str | None = Field(
            default=None,
            description="Varsa tarih araligi, frekans, kaynak veya analiz kisitlari.",
        )

    class Output(BaseModel):
        success: bool
        plan_summary: str = Field(..., description="Analiz stratejisinin 1-2 cumlelik ozeti")
        sub_tasks: list[SubTask] = Field(default_factory=list)
        synthesis_guidance: str = Field(
            ...,
            description="Alt adimlar tamamlandiginda nihai cevabin nasil birlestirilecegi",
        )
        error: str | None = None

    def __init__(self, *, provider: LLMProvider | None = None) -> None:
        self.provider = provider

    def _get_provider(self) -> LLMProvider:
        if self.provider is None:
            self.provider = get_default_provider()
        return self.provider

    def run(self, params: Input) -> Output:
        query = params.complex_query.strip()
        if not query:
            return self.Output(
                success=False,
                plan_summary="Plan olusturulamadi.",
                sub_tasks=[],
                synthesis_guidance="Kullanici anlamli bir analiz sorusu vermelidir.",
                error="complex_query bos olamaz.",
            )

        try:
            response = self._get_provider().chat(
                messages=self._build_messages(params),
                tools=None,
                temperature=0.0,
                response_format={"type": "json_object"},
            )
            parsed = self._parse_json_content(response.content or "")
            return self.Output.model_validate(parsed)
        except (json.JSONDecodeError, ValidationError, Exception) as exc:
            logger.warning("analysis_planner LLM path failed; using fallback: %s", exc)
            return self._fallback_plan(query, params.context_hint)

    def _build_messages(self, params: Input) -> list[dict[str, str]]:
        schema = self.Output.model_json_schema()
        user_content = params.complex_query
        if params.context_hint:
            user_content += f"\n\nEk baglam: {params.context_hint}"

        return [
            {
                "role": "system",
                "content": (
                    "Sen veri ve zaman serisi analiz sorularini planlayan bir aractin. "
                    "Yalnizca gecerli JSON dondur. focus_query degerlerini 2-5 kelimelik "
                    "arama ifadeleri olarak yaz; tarih ve frekans kisitlarini ayri alanlarda tut. "
                    "Korelasyonu nedensellik gibi sunma."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Asagidaki soruyu bu JSON semasina gore alt gorevlere ayir:\n"
                    f"{json.dumps(schema, ensure_ascii=False)}\n\nSoru:\n{user_content}"
                ),
            },
        ]

    @staticmethod
    def _parse_json_content(content: str) -> dict[str, Any]:
        text = content.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
            text = re.sub(r"\s*```$", "", text)
        return json.loads(text)

    def _fallback_plan(self, query: str, context_hint: str | None) -> Output:
        date_range = _extract_date_range(" ".join(part for part in [query, context_hint or ""] if part))
        frequency_hint = _extract_frequency_hint(query, context_hint)
        concepts = _extract_focus_concepts(query)

        sub_tasks: list[SubTask] = []
        for concept in concepts[:4]:
            sub_tasks.append(
                SubTask(
                    step=len(sub_tasks) + 1,
                    objective=f"{concept} ile ilgili uygun seri veya veri kaynagini bul",
                    focus_query=concept,
                    expected_output=f"{concept} icin seri, kaynak veya kullanilabilir veri",
                    constraints=["yerel katalog oncelikli", "gerekirse resmi kaynak veya web aramasi"],
                    date_range=date_range,
                    frequency_hint=frequency_hint,
                    analysis_type="lookup",
                )
            )

        if _needs_relationship_step(query) or len(sub_tasks) > 1:
            sub_tasks.append(
                SubTask(
                    step=len(sub_tasks) + 1,
                    objective="Bulunan serileri ortak donemde hizalayip iliskiyi temkinli yorumla",
                    focus_query="ortak donem korelasyon",
                    expected_output="Karsilastirma, korelasyon veya sentez bulgusu",
                    constraints=["yalnizca tool ciktisina dayali yorum yap", "korelasyonu nedensellik gibi sunma"],
                    date_range=date_range,
                    frequency_hint=frequency_hint,
                    analysis_type=_infer_analysis_type(query),
                )
            )

        if not sub_tasks:
            focus_query = _clean_focus_query(query)
            sub_tasks.append(
                SubTask(
                    step=1,
                    objective="Sorudaki ana veri kavramini bul",
                    focus_query=focus_query,
                    expected_output="Ilgili seri veya kaynak adayi",
                    constraints=["yerel katalog oncelikli"],
                    date_range=date_range,
                    frequency_hint=frequency_hint,
                    analysis_type="lookup",
                )
            )

        return self.Output(
            success=True,
            plan_summary=(
                "LLM ciktisi kullanilamadigi icin kural tabanli plan uretildi; "
                "ana kavramlar ayri aranip son adimda sentezlenecek."
            ),
            sub_tasks=sub_tasks,
            synthesis_guidance=(
                "Once her alt gorevde bulunan seri, kaynak ve tarih araligini belirt; sonra ortak "
                "donemdeki yon, guc ve veri sinirlarini acikla. Korelasyonu nedensellik gibi sunma."
            ),
            error=None,
        )


def _extract_date_range(text: str) -> str | None:
    years = re.findall(r"\b(20\d{2}|19\d{2})\b", text)
    if not years:
        return None
    unique_years = list(dict.fromkeys(years))
    if len(unique_years) == 1:
        return unique_years[0]
    return f"{unique_years[0]}..{unique_years[-1]}"


def _extract_frequency_hint(query: str, context_hint: str | None) -> str | None:
    text = f"{query} {context_hint or ''}".casefold()
    if any(term in text for term in ["gunluk", "günlük", "daily"]):
        return "daily"
    if any(term in text for term in ["haftalik", "haftalık", "weekly"]):
        return "weekly"
    if any(term in text for term in ["aylik", "aylık", "monthly"]):
        return "monthly"
    if _extract_date_range(text):
        return "monthly"
    return None


def _infer_analysis_type(query: str) -> str:
    text = query.casefold()
    if any(term in text for term in ["korelasyon", "baginti", "bağıntı", "iliski", "ilişki"]):
        return "correlation"
    if any(term in text for term in ["karsilastir", "karşılaştır", "kiyas", "kıyas"]):
        return "comparison"
    if "trend" in text:
        return "trend"
    if any(term in text for term in ["etki", "nedensellik"]):
        return "comparison"
    return "comparison"


def _needs_relationship_step(query: str) -> bool:
    text = query.casefold()
    return any(
        term in text
        for term in [
            "korelasyon",
            "baginti",
            "bağıntı",
            "iliski",
            "ilişki",
            "karsilastir",
            "karşılaştır",
            "etki",
            "nedensellik",
        ]
    )


def _extract_focus_concepts(query: str) -> list[str]:
    text = _strip_dates(query)
    text = re.sub(r"\barasindaki\b.*$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\barasındaki\b.*$", "", text, flags=re.IGNORECASE)
    parts = re.split(r"\s+(?:ile|ve|veya)\s+", text, flags=re.IGNORECASE)
    concepts: list[str] = []
    for part in parts:
        focus = _clean_focus_query(part)
        if focus and focus not in concepts:
            concepts.append(focus)
    return concepts


def _strip_dates(text: str) -> str:
    text = re.sub(r"\b(?:20\d{2}|19\d{2})\b", " ", text)
    text = re.sub(r"\b(?:yilinda|yılında|yili|yılı|aylik|aylık|monthly|weekly|daily)\b", " ", text, flags=re.IGNORECASE)
    return text


def _clean_focus_query(text: str) -> str:
    cleaned = _strip_dates(text)
    cleaned = _CONNECTOR_RE.sub(" ", cleaned)
    cleaned = re.sub(r"[^\w\sçğıöşüÇĞİÖŞÜ]", " ", cleaned, flags=re.UNICODE)
    tokens = [token.casefold() for token in cleaned.split() if len(token) > 1]
    normalised = [_normalise_token(token) for token in tokens]
    normalised = [token for token in normalised if token not in {"bir", "bu", "su", "şu"}]
    return " ".join(normalised[:5]).strip()


def _normalise_token(token: str) -> str:
    replacements = {
        "faizleri": "faiz",
        "faizler": "faiz",
        "oranlari": "oran",
        "oranları": "oran",
        "kredileri": "kredileri",
        "tufesi": "tufe",
        "tüfesi": "tufe",
        "tüfe": "tufe",
    }
    return replacements.get(token, token)
