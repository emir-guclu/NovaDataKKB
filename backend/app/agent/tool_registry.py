from __future__ import annotations

import json

from backend.app.tools.base import BaseTool


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        if not tool.name:
            raise ValueError("Tool name bos olamaz.")

        if tool.name in self._tools:
            raise ValueError(f"Tool zaten kayitli: {tool.name}")

        self._tools[tool.name] = tool

    def get(self, name: str) -> BaseTool | None:
        return self._tools.get(name)

    def list_tools(self) -> list[BaseTool]:
        return list(self._tools.values())

    def to_openai_tools_format(self) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.Input.model_json_schema(),
                },
            }
            for tool in self.list_tools()
        ]

    def to_prompt_description(self) -> str:
        blocks: list[str] = []

        for tool in self.list_tools():
            schema = tool.Input.model_json_schema()
            blocks.append(
                "\n".join(
                    [
                        f"Tool: {tool.name}",
                        f"Aciklama: {tool.description}",
                        "Parametre semasi:",
                        json.dumps(schema, ensure_ascii=False, indent=2),
                    ]
                )
            )

        return "\n\n".join(blocks)


def create_default_tool_registry() -> ToolRegistry:
    from backend.app.tools.anomaly_detection import AnomalyDetectionTool
    from backend.app.tools.causality_check import CausalityCheckTool
    from backend.app.tools.change_detection import ChangeDetectionTool
    from backend.app.tools.lakehouse_query import LakehouseQueryTool
    from backend.app.tools.series_catalog_search import SeriesCatalogSearchTool
    from backend.app.tools.web_search import WebSearchTool
    from backend.app.tools.web_url_reader import WebUrlReaderTool

    registry = ToolRegistry()
    registry.register(SeriesCatalogSearchTool())
    registry.register(ChangeDetectionTool())
    registry.register(WebSearchTool())
    registry.register(WebUrlReaderTool())
    registry.register(LakehouseQueryTool())
    registry.register(CausalityCheckTool())
    registry.register(AnomalyDetectionTool())
    return registry
