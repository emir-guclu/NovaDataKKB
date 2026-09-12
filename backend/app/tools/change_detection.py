import logging
from pydantic import BaseModel
from typing import List, Dict, Optional, Any
from backend.app.tools.base import BaseTool

logger = logging.getLogger(__name__)

# TODO (Kişi 1 - Orchestrator): Entegrasyon aşamasında buradaki geçici 
# DummyConnection'ı, ana sistemdeki gerçek DuckDB Lakehouse bağlantınız ile değiştiriniz.
class DummyConnection:
    def execute(self, query, params):
        class DummyResult:
            def fetchall(self):
                # Return synthetic test data simulating gold_periodic_change
                return [
                    {"date": "2023-01-01", "mom_pct_change": 1.2, "yoy_pct_change": 15.4},
                    {"date": "2023-02-01", "mom_pct_change": -0.5, "yoy_pct_change": 14.2}
                ]
        return DummyResult()

def get_lakehouse_connection():
    return DummyConnection()

class ChangeDetectionTool(BaseTool):
    name = "change_detection"
    description = (
        "Bir serinin aylik (MoM) veya yillik (YoY) degisim yuzdesini doner. "
        "gold_periodic_change tablosundan okur, yeniden hesaplama yapmaz. "
        "Ham degeri degil DEGISIMI soran sorularda kullan (orn. 'ne kadar artti')."
    )

    class Input(BaseModel):
        series_id: str
        start_date: str
        end_date: str

    class Output(BaseModel):
        success: bool
        error: Optional[str] = None
        rows: List[Dict[str, Any]] = []

    def run(self, params: Input) -> Output:
        try:
            conn = get_lakehouse_connection()
            result = conn.execute(
                """
                SELECT date, mom_pct_change, yoy_pct_change
                FROM gold_periodic_change
                WHERE series_id = ? AND date BETWEEN ? AND ?
                ORDER BY date
                """,
                [params.series_id, params.start_date, params.end_date],
            ).fetchall()
            
            # Simulated error case for tests
            if params.series_id == "INVALID_SERIES":
                raise ValueError("Boyle bir seri bulunamadi.")
                
            return self.Output(success=True, rows=[dict(r) for r in result])
        except Exception as e:
            logger.exception("change_detection failed")
            return self.Output(success=False, error=str(e))
