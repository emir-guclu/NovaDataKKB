import logging
from pydantic import BaseModel
from typing import List, Dict, Optional, Any
try:
    from ddgs import DDGS
except ImportError:
    from duckduckgo_search import DDGS

from backend.app.tools.base import BaseTool

logger = logging.getLogger(__name__)

class WebSearchTool(BaseTool):
    name = "web_search"
    description = (
        "Internette guncel bilgi arar. Sistemdeki (BDDK/EVDS/FinTurk) veriyle "
        "cevaplanamayan, guncel/harici bilgi gerektiren sorularda kullan. "
        "Lakehouse'daki mevcut veriyi aramak icin KULLANMA, o is lakehouse_query'nin."
    )

    class Input(BaseModel):
        query: str

    class Output(BaseModel):
        success: bool
        error: Optional[str] = None
        results: List[Dict[str, Any]] = []

    def run(self, params: Input) -> Output:
        try:
            # Simulated error case for tests
            if params.query == "ERROR_TRIGGER":
                raise Exception("Simulated network error")
                
            with DDGS(timeout=5) as ddgs:
                raw_results = list(ddgs.text(params.query, max_results=3))
            
            results = []
            for r in raw_results:
                results.append({
                    "title": r.get("title", ""),
                    "url": r.get("href", ""),
                    "snippet": r.get("body", "")
                })
                
            return self.Output(success=True, results=results)
        except Exception as e:
            logger.exception("web_search failed")
            return self.Output(success=False, error=str(e))
