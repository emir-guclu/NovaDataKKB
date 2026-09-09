"""EVDS Module for raw data ingestion, catalog discovery, and API integration."""
from app.modules.evds.catalog import discover_all
from app.modules.evds.catalog_store import load_catalog, save_catalog, update_series_status
from app.modules.evds.client import EvdsClient
from app.modules.evds.ingestion import ingest_series

__all__ = [
    "EvdsClient",
    "ingest_series",
    "discover_all",
    "load_catalog",
    "save_catalog",
    "update_series_status",
]

