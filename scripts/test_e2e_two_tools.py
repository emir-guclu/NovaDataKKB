from __future__ import annotations

import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

from backend.app.agent.loop import run_agent
from backend.app.agent.tool_registry import ToolRegistry
from backend.app.core.llm_provider import KloudeksProvider
from backend.app.tools.anomaly_detection import AnomalyDetectionTool
from backend.app.tools.causality_check import CausalityCheckTool
from backend.app.tools.change_detection import ChangeDetectionTool
from backend.app.tools.lakehouse_query import LakehouseQueryTool
from backend.app.tools.web_search import WebSearchTool


def main() -> None:
    load_dotenv()
    logging.basicConfig(level=logging.INFO)

    registry = ToolRegistry()
    registry.register(ChangeDetectionTool())
    registry.register(WebSearchTool())
    registry.register(LakehouseQueryTool())
    registry.register(CausalityCheckTool())
    registry.register(AnomalyDetectionTool())

    provider = KloudeksProvider()

    questions = [
        "Konut kredisi hacmi gecen aya gore nasil degisti?",
        "Turkiye'nin guncel enflasyon orani hakkinda en son haberler neler?",
    ]

    for question in questions:
        print(f"SORU: {question}")
        answer = run_agent(question, registry, provider)
        print(f"CEVAP: {answer}")
        print("=" * 60)


if __name__ == "__main__":
    main()
