"""EVDS API Client wrapper supporting multi-key rotation and rate-limit handling."""
import logging
import os
from datetime import datetime, timedelta
from functools import partial
from typing import Any, List, Optional, Tuple, Union
import pandas as pd
import requests
from evds import evdsAPI

logger = logging.getLogger(__name__)

# Maximum number of backwards pagination pages to fetch when the EVDS 1000-records limit is hit.
# Each EVDS page returns up to 1000 records. 10 pages * 1000 = 10,000 days (~27 years of daily data).
# This provides an ample historical buffer for long series (our 2021-2026 requirement spans ~1978 days / 2 pages)
# while acting as an absolute safety ceiling against infinite loops (W-02).
DEFAULT_MAX_PAGINATION_PAGES: int = 10
EVDS_REQUEST_TIMEOUT_SECONDS: float = 75.0


class EvdsClient:
    """Wrapper around the EVDS Python API client with automatic key rotation."""

    def __init__(self, api_keys: Optional[List[str]] = None) -> None:
        """Initialize the EVDS client with a pool of API keys.

        Args:
            api_keys: Optional list of API keys. If not provided, keys will be
                      loaded from environment variables (EVDS_API_KEY_1..4).
        """
        if api_keys is not None:
            self.api_keys = [k for k in api_keys if k]
        else:
            self.api_keys = self._load_keys_from_env()

        self._current_key_idx = 0

    def _load_keys_from_env(self) -> List[str]:
        """Loads all available EVDS API keys from environment variables."""
        keys: List[str] = []
        # Check standard 1 to 4 keys first
        for i in range(1, 10):
            key = os.getenv(f"EVDS_API_KEY_{i}")
            if key and key.strip():
                keys.append(key.strip())

        # Fallback to single EVDS_API_KEY if none found
        if not keys:
            single_key = os.getenv("EVDS_API_KEY")
            if single_key and single_key.strip():
                keys.append(single_key.strip())

        return keys

    @property
    def current_key(self) -> Optional[str]:
        """Returns the currently active API key."""
        if not self.api_keys:
            return None
        return self.api_keys[self._current_key_idx]

    def _rotate_key(self) -> None:
        """Rotates to the next available API key in the pool."""
        if not self.api_keys:
            return
        old_idx = self._current_key_idx
        self._current_key_idx = (self._current_key_idx + 1) % len(self.api_keys)
        logger.warning(
            f"Rotating EVDS API key from index {old_idx} (Key #{old_idx + 1}) "
            f"to index {self._current_key_idx} (Key #{self._current_key_idx + 1})."
        )

    def _create_api_instance(self, api_key: str) -> Any:
        """EVDS istemcisini sonlu bir HTTP timeout ile olusturur."""
        api_instance = evdsAPI(key=api_key)
        api_instance.session.get = partial(
            api_instance.session.get,
            timeout=EVDS_REQUEST_TIMEOUT_SECONDS,
        )
        return api_instance

    def _execute_with_rotation(self, operation_name: str, op_callable: Any) -> Any:
        """Executes an API call with automatic key rotation upon encountering HTTP 429 or rate limits."""
        if not self.api_keys:
            raise RuntimeError("No EVDS API keys configured in environment or client.")

        total_keys = len(self.api_keys)
        attempts = 0
        last_exception: Optional[Exception] = None

        while attempts < total_keys:
            active_key = self.current_key
            logger.debug(f"Attempting EVDS request with key index {self._current_key_idx} for {operation_name}")

            try:
                api_instance = self._create_api_instance(active_key)
                return op_callable(api_instance)
            except requests.exceptions.HTTPError as http_err:
                last_exception = http_err
                status_code = getattr(http_err.response, "status_code", None)
                if status_code == 429 or "429" in str(http_err) or "rate limit" in str(http_err).lower():
                    logger.warning(
                        f"Rate limit (HTTP 429) encountered on key index {self._current_key_idx} "
                        f"for {operation_name}. Rotating key."
                    )
                    self._rotate_key()
                    attempts += 1
                else:
                    logger.error(f"HTTP error {status_code} occurred while requesting {operation_name}: {http_err}")
                    raise
            except Exception as exc:
                last_exception = exc
                err_msg = str(exc).lower()
                if "429" in err_msg or "rate limit" in err_msg or "too many requests" in err_msg:
                    logger.warning(
                        f"Rate limit detected in error message for {operation_name}. Rotating key."
                    )
                    self._rotate_key()
                    attempts += 1
                else:
                    logger.error(f"Unexpected error while requesting {operation_name}: {exc}")
                    raise

        error_detail = f"All {total_keys} EVDS API keys exhausted (Rate limit / HTTP 429). Last error: {last_exception}"
        logger.critical(error_detail)
        raise RuntimeError(error_detail)

    def get_data(
        self,
        series_code: str,
        start_date: str,
        end_date: str,
        raw: bool = True,
        max_pages: Optional[int] = None,
        **kwargs: Any,
    ) -> Any:
        """Fetches series data from EVDS API with automatic key rotation and pagination.

        If the response hits EVDS's hard limit of 1000 records, it automatically
        fetches remaining earlier historical dates in pages to prevent silent truncation.

        Args:
            series_code: EVDS series code (e.g., 'TP.KTF10').
            start_date: Start date string formatted as DD-MM-YYYY.
            end_date: End date string formatted as DD-MM-YYYY.
            raw: Whether to return raw JSON payload from TCMB.
            max_pages: Optional maximum number of backward pagination pages (defaults to DEFAULT_MAX_PAGINATION_PAGES).
            **kwargs: Additional parameters for EVDS API.

        Returns:
            Raw response payload (list of dicts or DataFrame) from EVDS.
        """
        series_param = [series_code] if isinstance(series_code, str) else list(series_code)
        pagination_limit = max_pages if max_pages is not None else DEFAULT_MAX_PAGINATION_PAGES

        def _fetch_window(api: Any, s_date: str, e_date: str) -> Any:
            res = api.get_data(
                series_param,
                startdate=s_date,
                enddate=e_date,
                raw=raw,
                **kwargs,
            )
            if res is None:
                raise RuntimeError(f"EVDS API returned None for series '{series_code}'.")
            return res

        # 1. First fetch for requested date range
        initial_res = self._execute_with_rotation(
            f"series '{series_code}' ({start_date}..{end_date})",
            lambda api: _fetch_window(api, start_date, end_date),
        )

        # If raw list and hit the 1000 limit, paginate backwards
        if raw and isinstance(initial_res, list) and len(initial_res) == 1000:
            all_records = list(initial_res)
            page = 1

            while page <= pagination_limit:
                earliest_item = all_records[0]
                if not isinstance(earliest_item, dict) or "Tarih" not in earliest_item:
                    break

                earliest_date_str = str(earliest_item["Tarih"]).strip()
                try:
                    earliest_dt = datetime.strptime(earliest_date_str, "%d-%m-%Y")
                    start_dt = datetime.strptime(start_date, "%d-%m-%Y")
                except ValueError:
                    # Non-standard or monthly date format, stop pagination
                    break

                # If we have already reached or surpassed start_date, we have the full history
                if earliest_dt <= start_dt:
                    break

                # Query remaining range up to day before earliest_dt
                next_end_dt = earliest_dt - timedelta(days=1)
                if next_end_dt < start_dt:
                    break

                next_end_str = next_end_dt.strftime("%d-%m-%Y")
                logger.info(
                    f"Series '{series_code}' hit 1000 records limit. "
                    f"Fetching earlier page: {start_date} to {next_end_str}..."
                )

                chunk = self._execute_with_rotation(
                    f"series '{series_code}' (earlier page {start_date}..{next_end_str})",
                    lambda api, ne=next_end_str: _fetch_window(api, start_date, ne),
                )

                if not isinstance(chunk, list) or not chunk:
                    break

                # Prepend earlier chunk
                all_records = list(chunk) + all_records
                page += 1

                # If earlier chunk returned fewer than 1000 items, we got all history
                if len(chunk) < 1000:
                    break

            # Deduplicate by Tarih preserving order
            seen_dates = set()
            deduped_records = []
            for item in all_records:
                if isinstance(item, dict) and "Tarih" in item:
                    t = item["Tarih"]
                    if t in seen_dates:
                        continue
                    seen_dates.add(t)
                deduped_records.append(item)

            return deduped_records

        return initial_res

    def get_main_categories(self, **kwargs: Any) -> Any:
        """Fetches main categories from EVDS API with automatic key rotation."""
        def _fetch_cats(api: Any) -> Any:
            if hasattr(api, "get_main_categories") and callable(api.get_main_categories):
                return api.get_main_categories(**kwargs)
            return getattr(api, "main_categories", None)

        return self._execute_with_rotation("main categories", _fetch_cats)

    def get_sub_categories(self, category_id: Union[int, str], **kwargs: Any) -> Any:
        """Fetches subcategories (datagroups) for a given category ID with automatic key rotation."""
        return self._execute_with_rotation(
            f"subcategories for category {category_id}",
            lambda api: api.get_sub_categories(category_id, **kwargs),
        )

    def get_series(self, datagroup_code: str, **kwargs: Any) -> Any:
        """Fetches series list for a given datagroup code with automatic key rotation."""
        return self._execute_with_rotation(
            f"series for datagroup {datagroup_code}",
            lambda api: api.get_series(datagroup_code, **kwargs),
        )

    def get_series_metadata(self, series_code: str) -> Optional[List[dict[str, Any]]]:
        """Fetches rich metadata for a given series code via catalog and EVDS API."""
        try:
            from app.modules.evds.metadata import fetch_single_series_metadata
        except ModuleNotFoundError:
            from backend.app.modules.evds.metadata import fetch_single_series_metadata

        meta = fetch_single_series_metadata(series_code, client=self)
        if meta:
            return [meta]
        return None


