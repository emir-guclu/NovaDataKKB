import json

from backend.app.core.llm_provider import LLMResponse
from backend.app.tools.analysis_planner import AnalysisPlannerTool


class FakePlannerProvider:
    def __init__(self, content: str | None = None, exc: Exception | None = None) -> None:
        self.content = content
        self.exc = exc
        self.calls = []

    def chat(self, messages, tools=None, temperature=None, response_format=None):
        self.calls.append(
            {
                "messages": messages,
                "tools": tools,
                "temperature": temperature,
                "response_format": response_format,
            }
        )
        if self.exc:
            raise self.exc
        return LLMResponse(
            content=self.content,
            tool_calls=[],
            finish_reason="stop",
            raw=None,
        )

    def embed(self, text: str) -> list[float]:
        return [0.0]


def test_analysis_planner_validates_llm_json_and_passes_structured_output_options():
    payload = {
        "success": True,
        "plan_summary": "Mevduat faizi ve tuketici kredileri ayri bulunup iliski temkinli yorumlanacak.",
        "sub_tasks": [
            {
                "step": 1,
                "objective": "Mevduat faiz oranini temsil eden seriyi bul",
                "focus_query": "mevduat faiz",
                "expected_output": "Mevduat faiz serisi",
                "constraints": ["yerel katalog oncelikli"],
                "date_range": "2024",
                "frequency_hint": "monthly",
                "analysis_type": "lookup",
            },
            {
                "step": 2,
                "objective": "Tuketici kredileri serisini bul",
                "focus_query": "tuketici kredileri",
                "expected_output": "Tuketici kredi serisi",
                "constraints": ["BDDK veya EVDS"],
                "date_range": "2024",
                "frequency_hint": "monthly",
                "analysis_type": "lookup",
            },
            {
                "step": 3,
                "objective": "Ortak donemde bagintiyi yorumla",
                "focus_query": "ortak donem korelasyon",
                "expected_output": "Korelasyon ve veri sinirlari",
                "constraints": ["korelasyonu nedensellik gibi sunma"],
                "date_range": "2024",
                "frequency_hint": "monthly",
                "analysis_type": "correlation",
            },
        ],
        "synthesis_guidance": "Serileri kaynaklariyla belirt; korelasyonu nedensellik gibi sunma.",
        "error": None,
    }
    provider = FakePlannerProvider(content=json.dumps(payload))
    tool = AnalysisPlannerTool(provider=provider)

    result = tool.run(
        tool.Input(
            complex_query="2024 yilinda mevduat faizleri ile tuketici kredileri arasindaki bagintiyi incele"
        )
    )

    assert result.success is True
    assert len(result.sub_tasks) == 3
    assert result.sub_tasks[0].focus_query == "mevduat faiz"
    assert provider.calls[0]["temperature"] == 0.0
    assert provider.calls[0]["response_format"] == {"type": "json_object"}
    assert provider.calls[0]["tools"] is None


def test_analysis_planner_fallback_decomposes_complex_question_when_provider_fails():
    provider = FakePlannerProvider(exc=RuntimeError("provider down"))
    tool = AnalysisPlannerTool(provider=provider)

    result = tool.run(
        tool.Input(
            complex_query="2024 yilinda mevduat faizleri ile tuketici kredileri arasindaki bagintiyi incele"
        )
    )

    assert result.success is True
    assert "kural tabanli" in result.plan_summary.lower()
    assert len(result.sub_tasks) >= 3
    focus_queries = [task.focus_query for task in result.sub_tasks]
    assert "mevduat faiz" in focus_queries
    assert "tuketici kredileri" in focus_queries
    assert any(task.analysis_type == "correlation" for task in result.sub_tasks)
    assert all("2024" not in task.focus_query for task in result.sub_tasks)
    assert {task.date_range for task in result.sub_tasks} == {"2024"}
    assert {task.frequency_hint for task in result.sub_tasks} == {"monthly"}


def test_analysis_planner_fallback_handles_invalid_json():
    provider = FakePlannerProvider(content="{not-json")
    tool = AnalysisPlannerTool(provider=provider)

    result = tool.run(tool.Input(complex_query="Konut kredisi faizleri ile TUFE korelasyonunu karsilastir"))

    assert result.success is True
    assert result.error is None
    assert len(result.sub_tasks) >= 3
