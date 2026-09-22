from __future__ import annotations

import logging
import sys
from datetime import date
from pathlib import Path
from typing import Any, Callable, Literal

import pandas as pd
from pydantic import BaseModel, Field

try:
    from backend.app.tools.base import BaseTool
except ModuleNotFoundError:
    from app.tools.base import BaseTool

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
BACKEND_DIR = PROJECT_ROOT / "backend"
DEFAULT_CATALOG_PATH = PROJECT_ROOT / "data" / "bronze" / "evds" / "evds_catalog.parquet"


class EvdsSeriesMatch(BaseModel):
    series_code: str
    series_name: str
    datagroup_name: str
    frequency: str


def _default_loader(**kwargs: Any) -> dict[str, Any]:
    if str(BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(BACKEND_DIR))
    from app.services.evds_loader import load_evds_series

    return load_evds_series(**kwargs)


def _as_text(value: Any) -> str:
    if pd.isna(value):
        return ""
    return str(value)


class EvdsTool(BaseTool):
    name = "evds_data_service"
    description = (
        "TCMB EVDS resmi veri servisinden canli seri arar veya indirir. Lakehouse katalogunda "
        "bulunmayan Merkez Bankasi serileri icin kullanilir. Haber veya tahmin uretmek icin "
        "KULLANMA; resmi seri gerekiyorsa action='search' ile katalogda ara, action='load' ile "
        "seri kodunu vererek veriyi indir ve son degerini getir."
    )

    class Input(BaseModel):
        action: Literal["search", "load"] = Field(
            default="search",
            description="'search': EVDS katalogunda seri arar. 'load': Belirtilen seriyi resmi API'den cekip yukler.",
        )
        query: str | None = Field(
            default=None,
            description="Arama terimi (action='search' ise zorunlu).",
        )
        series_code: str | None = Field(
            default=None,
            description="EVDS seri kodu (action='load' ise zorunlu).",
        )
        start_date: str = Field(
            default="01-01-2021",
            description="Baslangic tarihi (DD-MM-YYYY formatinda).",
        )
        end_date: str | None = Field(
            default=None,
            description="Bitis tarihi (DD-MM-YYYY formatinda, varsayilan bugunun tarihi).",
        )

    class Output(BaseModel):
        success: bool
        error: str | None = None
        action: str
        matches: list[EvdsSeriesMatch] = Field(default_factory=list)
        series_info: dict[str, Any] | None = None
        latest_value: float | None = None
        latest_date: str | None = None
        preview: list[dict[str, Any]] = Field(default_factory=list)
        message: str | None = None

    def __init__(
        self,
        *,
        catalog_path: str | Path = DEFAULT_CATALOG_PATH,
        loader: Callable[..., dict[str, Any]] | None = None,
        today: Callable[[], date] = date.today,
    ) -> None:
        self.catalog_path = Path(catalog_path)
        self.loader = loader or _default_loader
        self.today = today

    def run(self, params: Input) -> Output:
        try:
            if params.action == "search":
                return self._search(params)
            return self._load(params)
        except Exception as exc:
            logger.warning("evds_data_service call failed (%s): %s", params.action, exc)
            return self.Output(success=False, error=str(exc), action=params.action)

    def _search(self, params: Input) -> Output:
        query = (params.query or "").strip()
        if not query:
            return self.Output(success=False, error="query action='search' icin zorunludur.", action="search")
        if not self.catalog_path.exists():
            return self.Output(success=False, error=f"EVDS katalogu bulunamadi: {self.catalog_path}", action="search")

        catalog = pd.read_parquet(self.catalog_path)
        required_columns = {"series_code", "series_name", "datagroup_name", "frequency"}
        missing = required_columns - set(catalog.columns)
        if missing:
            return self.Output(success=False, error=f"EVDS katalog kolonlari eksik: {sorted(missing)}", action="search")

        terms = [term.casefold() for term in query.split() if term.strip()]
        searchable_columns = ["series_code", "series_name", "datagroup_name"]

        def score(row: pd.Series) -> int:
            haystack = " ".join(_as_text(row.get(column)) for column in searchable_columns).casefold()
            return sum(1 for term in terms if term in haystack)

        ranked = catalog.copy()
        ranked["_match_score"] = ranked.apply(score, axis=1)
        ranked["_is_archive"] = ranked["series_name"].astype(str).str.contains(r"ar[sş]iv", case=False, regex=True)
        ranked = ranked[ranked["_match_score"] > 0].sort_values(
            by=["_match_score", "_is_archive", "series_code"],
            ascending=[False, True, True],
        )

        matches = [
            EvdsSeriesMatch(
                series_code=_as_text(row["series_code"]),
                series_name=_as_text(row["series_name"]),
                datagroup_name=_as_text(row["datagroup_name"]),
                frequency=_as_text(row["frequency"]),
            )
            for _, row in ranked.head(10).iterrows()
        ]
        return self.Output(
            success=True,
            action="search",
            matches=matches,
            message=f"{len(matches)} seri bulundu." if matches else "Eslesen EVDS serisi bulunamadi.",
        )

    def _load(self, params: Input) -> Output:
        series_code = (params.series_code or "").strip()
        if not series_code:
            return self.Output(success=False, error="series_code action='load' icin zorunludur.", action="load")

        end_date = params.end_date or self.today().strftime("%d-%m-%Y")
        summary = self.loader(
            series_code=series_code,
            start_date=params.start_date,
            end_date=end_date,
            context="live",
            add_to_silver=True,
        )
        preview = list(summary.get("preview") or [])
        series_info = {
            key: summary.get(key)
            for key in [
                "status",
                "series_id",
                "series_code",
                "series_name",
                "freq",
                "unit",
                "rows_count",
                "first_date",
                "last_date",
                "added_to_silver",
                "added_to_aligned",
            ]
        }
        return self.Output(
            success=True,
            action="load",
            series_info=series_info,
            latest_value=summary.get("latest_value"),
            latest_date=summary.get("last_date"),
            preview=preview,
            message=summary.get("message"),
        )
