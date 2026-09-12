import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

api_key = os.getenv("MIA_API_KEY")
if not api_key:
    raise RuntimeError("MIA_API_KEY is not set")

client = OpenAI(
    api_key=api_key,
    base_url="https://mia.csp.kloudeks.com/v1",
)

MODEL = "kkbhackathon2026/Qwen3.8-27B"

CASES = [
    {
        "name": "simple_weather",
        "prompt": "İstanbul'da hava nasıl?",
        "tools": [{
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "Bir şehrin hava durumunu döndürür",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "city": {"type": "string"}
                    },
                    "required": ["city"],
                },
            },
        }],
    },
    {
        "name": "lakehouse_query",
        "prompt": "2025 yılındaki konut kredisi faiz oranını lakehouse üzerinden sorgula.",
        "tools": [{
            "type": "function",
            "function": {
                "name": "query_lakehouse",
                "description": "Lakehouse içindeki analitik tablolardan veri sorgular",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "table": {"type": "string"},
                        "columns": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "filters": {
                            "type": "object",
                            "additionalProperties": {
                                "type": ["string", "number", "boolean"]
                            },
                        },
                    },
                    "required": ["table", "columns"],
                },
            },
        }],
    },
    {
        "name": "nested_analysis",
        "prompt": "Konut kredisi faizleri ile konut satışlarını 2024-2025 dönemi için karşılaştır.",
        "tools": [{
            "type": "function",
            "function": {
                "name": "compare_series",
                "description": "İki finansal göstergeyi belirli dönem ve agregasyonla karşılaştırır",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "series": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"},
                                    "source": {
                                        "type": "string",
                                        "enum": ["EVDS", "BDDK", "GOLD"],
                                    },
                                },
                                "required": ["name", "source"],
                            },
                            "minItems": 2,
                        },
                        "period": {
                            "type": "object",
                            "properties": {
                                "start": {"type": "string"},
                                "end": {"type": "string"},
                            },
                            "required": ["start", "end"],
                        },
                    },
                    "required": ["series", "period"],
                },
            },
        }],
    },
]

for case in CASES:
    print(f"\\n=== {case['name']} ===")
    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": case["prompt"]}],
            tools=case["tools"],
            tool_choice="auto",
            temperature=0.0,
        )

        choice = response.choices[0]
        message = choice.message

        print("finish_reason:", choice.finish_reason)
        print("tool_calls:", message.tool_calls)
        print("content:", message.content)

    except Exception as exc:
        print("ERROR:", type(exc).__name__, str(exc))
