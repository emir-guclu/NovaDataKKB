from __future__ import annotations

import argparse
import os
import sys
import time
from typing import Any

import requests


DEFAULT_BASE_URL = os.getenv(
    "API_BASE_URL",
    "http://127.0.0.1:8000",
).rstrip("/")

CLIENT_TIMEOUT_SECONDS = float(
    os.getenv("CLIENT_TIMEOUT_SECONDS", "115")
)

SLOW_SUCCESS_QUESTION = os.getenv(
    "SLOW_SUCCESS_QUESTION",
    (
        "TCMB EVDS resmi veri servisinden TP.DK.USD.A.YTL serisini "
        "01-01-2021 tarihinden bugüne kadar getir. "
        "Son değeri ve tarihini açıkça belirt."
    ),
)

TIMEOUT_TEST_QUESTION = os.getenv(
    "TIMEOUT_TEST_QUESTION",
    SLOW_SUCCESS_QUESTION,
)


def post_question(
    base_url: str,
    question: str,
) -> tuple[requests.Response, float]:
    start = time.perf_counter()

    response = requests.post(
        f"{base_url}/api/v1/ask",
        json={"question": question},
        timeout=CLIENT_TIMEOUT_SECONDS,
    )

    elapsed = time.perf_counter() - start
    return response, elapsed


def parse_json(
    response: requests.Response,
) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError as exc:
        raise AssertionError(
            f"Response is not valid JSON. "
            f"HTTP {response.status_code}: "
            f"{response.text[:500]}"
        ) from exc

    if not isinstance(payload, dict):
        raise AssertionError(
            f"Expected JSON object, got: "
            f"{type(payload).__name__}"
        )

    return payload


def check_health(
    base_url: str,
) -> None:
    response = requests.get(
        f"{base_url}/health",
        timeout=10,
    )
    response.raise_for_status()

    payload = parse_json(response)

    if payload.get("status") != "ok":
        raise AssertionError(
            f"Unexpected /health payload: {payload}"
        )

    print(f"[PASS] health: {base_url}/health")


def run_slow_success(
    base_url: str,
) -> None:
    print("[RUN ] slow-success EVDS scenario")

    response, elapsed = post_question(
        base_url,
        SLOW_SUCCESS_QUESTION,
    )
    payload = parse_json(response)

    if response.status_code != 200:
        raise AssertionError(
            f"Expected HTTP 200, got "
            f"{response.status_code}: {payload}"
        )

    if payload.get("success") is not True:
        raise AssertionError(
            f"Expected successful response, "
            f"got after {elapsed:.2f}s: {payload}"
        )

    answer = (
        (payload.get("data") or {})
        .get("answer", "")
        .strip()
    )

    if not answer:
        raise AssertionError(
            "Successful response did not "
            "contain data.answer"
        )

    print(
        f"[PASS] slow-success completed "
        f"in {elapsed:.2f}s"
    )
    print(
        f"[INFO] answer preview: "
        f"{answer[:240]!r}"
    )


def run_expected_timeout(
    base_url: str,
) -> None:
    print("[RUN ] expected-timeout scenario")
    print(
        "[INFO] Run this mode only against "
        "local/staging with "
        "REQUEST_HARD_TIMEOUT_SECONDS "
        "temporarily lowered, e.g. 5."
    )

    response, elapsed = post_question(
        base_url,
        TIMEOUT_TEST_QUESTION,
    )
    payload = parse_json(response)

    if response.status_code != 200:
        raise AssertionError(
            f"Expected HTTP 200 application "
            f"timeout envelope, got "
            f"{response.status_code}: {payload}"
        )

    if payload.get("success") is not False:
        raise AssertionError(
            "Expected success=false. "
            "The request may have completed "
            "before the temporary hard timeout. "
            f"Elapsed={elapsed:.2f}s "
            f"payload={payload}"
        )

    error = str(
        payload.get("error") or ""
    )

    timeout_markers = (
        "zaman aşım",
        "timeout",
        "timed out",
    )

    if not any(
        marker in error.casefold()
        for marker in timeout_markers
    ):
        raise AssertionError(
            f"Expected timeout error, got "
            f"after {elapsed:.2f}s: {payload}"
        )

    print(
        f"[PASS] controlled timeout "
        f"returned in {elapsed:.2f}s"
    )
    print(
        f"[INFO] error: {error}"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate NOVA slow-request and "
            "hard-timeout behavior."
        )
    )

    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help=(
            "API base URL "
            f"(default: {DEFAULT_BASE_URL})"
        ),
    )

    parser.add_argument(
        "--mode",
        choices=(
            "slow-success",
            "expect-timeout",
            "both",
        ),
        default="slow-success",
        help="Scenario to run.",
    )

    return parser


def main() -> int:
    args = build_parser().parse_args()
    base_url = args.base_url.rstrip("/")

    try:
        check_health(base_url)

        if args.mode in (
            "slow-success",
            "both",
        ):
            run_slow_success(base_url)

        if args.mode in (
            "expect-timeout",
            "both",
        ):
            run_expected_timeout(base_url)

    except (
        requests.RequestException,
        AssertionError,
    ) as exc:
        print(
            f"[FAIL] {exc}",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
