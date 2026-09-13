from __future__ import annotations

from datetime import date

import pandas as pd
import pytest
from pydantic import ValidationError

try:
    from backend.app.tools.evds_tool import EvdsTool
except ModuleNotFoundError:
    from app.tools.evds_tool import EvdsTool


def _write_catalog(path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(path, index=False)


def test_evds_search_catalog_returns_matching_series(tmp_path):
    catalog_path = tmp_path / "evds_catalog.parquet"
    _write_catalog(
        catalog_path,
        [
            {
                "datagroup_name": "Para ve Banka Istatistikleri",
                "series_code": "TP.RESERVE.GROSS",
                "series_name": "TCMB Brut Rezervler",
                "frequency": "Haftalik",
            },
            {
                "datagroup_name": "Fiyat Endeksleri",
                "series_code": "TP.FG.J0",
                "series_name": "Tuketici Fiyat Endeksi",
                "frequency": "Aylik",
            },
        ],
    )
    tool = EvdsTool(catalog_path=catalog_path)

    result = tool.run(tool.Input(action="search", query="brut rezerv"))

    assert result.success is True
    assert result.action == "search"
    assert result.error is None
    assert len(result.matches) == 1
    assert result.matches[0].series_code == "TP.RESERVE.GROSS"
    assert result.matches[0].series_name == "TCMB Brut Rezervler"
    assert result.matches[0].datagroup_name == "Para ve Banka Istatistikleri"
    assert result.matches[0].frequency == "Haftalik"
    assert "1 seri" in result.message


def test_evds_load_series_uses_live_context_and_returns_latest_value():
    calls = []

    def fake_loader(**kwargs):
        calls.append(kwargs)
        return {
            "status": "pending_review",
            "message": "Inceleme bekliyor.",
            "series_id": "EVDS:TP.TEST.LIVE",
            "series_code": "TP.TEST.LIVE",
            "series_name": "Live Test Series",
            "freq": "M",
            "unit": "TL",
            "rows_count": 2,
            "first_date": "2024-01-31",
            "last_date": "2024-02-29",
            "latest_value": 12.5,
            "added_to_silver": True,
            "added_to_aligned": False,
            "preview": [
                {"date": "2024-01-31", "value": 10.0},
                {"date": "2024-02-29", "value": 12.5},
            ],
        }

    tool = EvdsTool(loader=fake_loader, today=lambda: date(2024, 3, 2))

    result = tool.run(tool.Input(action="load", series_code="TP.TEST.LIVE", start_date="01-01-2024"))

    assert result.success is True
    assert result.action == "load"
    assert result.latest_value == 12.5
    assert result.latest_date == "2024-02-29"
    assert result.series_info == {
        "status": "pending_review",
        "series_id": "EVDS:TP.TEST.LIVE",
        "series_code": "TP.TEST.LIVE",
        "series_name": "Live Test Series",
        "freq": "M",
        "unit": "TL",
        "rows_count": 2,
        "first_date": "2024-01-31",
        "last_date": "2024-02-29",
        "added_to_silver": True,
        "added_to_aligned": False,
    }
    assert result.preview[-1] == {"date": "2024-02-29", "value": 12.5}
    assert result.message == "Inceleme bekliyor."
    assert calls == [
        {
            "series_code": "TP.TEST.LIVE",
            "start_date": "01-01-2024",
            "end_date": "02-03-2024",
            "context": "live",
            "add_to_silver": True,
        }
    ]


def test_invalid_inputs_return_structured_errors():
    tool = EvdsTool(loader=lambda **_: None)

    missing_series = tool.run(tool.Input(action="load"))
    missing_query = tool.run(tool.Input(action="search", query="  "))

    assert missing_series.success is False
    assert missing_series.action == "load"
    assert "series_code" in missing_series.error
    assert missing_query.success is False
    assert missing_query.action == "search"
    assert "query" in missing_query.error


def test_evds_tool_input_schema_rejects_unknown_action():
    with pytest.raises(ValidationError):
        EvdsTool.Input(action="download")
