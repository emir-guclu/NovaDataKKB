import json
import os
import duckdb
import pytest
from dotenv import load_dotenv
from app.core.llm_provider import KloudeksProvider

load_dotenv()
pytestmark = pytest.mark.skipif(not os.getenv("MIA_API_KEY"), reason="MIA_API_KEY not configured")

TOOLS = [{
    "type": "function",
    "function": {
        "name": "query_lakehouse",
        "description": "Gold konut kredisi piyasası tablosundan tarih aralığında veri sorgular",
        "parameters": {
            "type": "object",
            "properties": {
                "table": {"type": "string", "enum": ["gold_housing_credit_market"]},
                "start_date": {"type": "string"},
                "end_date": {"type": "string"},
            },
            "required": ["table", "start_date", "end_date"],
        },
    },
}]


def test_kloudeks_native_tool_call_loop():
    provider = KloudeksProvider()
    messages = [{"role": "user", "content": "2025 yılı konut kredisi piyasasını lakehouse verisiyle analiz et."}]

    first = provider.chat(messages, tools=TOOLS)
    assert first.finish_reason == "tool_calls"
    assert len(first.tool_calls) == 1

    call = first.tool_calls[0]
    assert call.name == "query_lakehouse"
    args = json.loads(call.arguments)
    assert args["table"] == "gold_housing_credit_market"

    gold_path = "data/gold/gold_housing_credit_market.parquet"
    con = duckdb.connect()
    rows = con.execute(
        "SELECT date, konut_kredisi_faiz_orani, toplam_konut_satisi FROM read_parquet(?) WHERE date BETWEEN ? AND ? ORDER BY date",
        [gold_path, args["start_date"], args["end_date"]],
    ).fetchall()
    con.close()
    assert rows

    messages += [
        {
            "role": "assistant",
            "content": first.content or "",
            "tool_calls": [{
                "id": call.id,
                "type": "function",
                "function": {"name": call.name, "arguments": call.arguments},
            }],
        },
        {"role": "tool", "tool_call_id": call.id, "content": json.dumps(rows, default=str)},
    ]

    final = provider.chat(messages, tools=TOOLS)
    assert final.finish_reason == "stop"
    assert final.content
