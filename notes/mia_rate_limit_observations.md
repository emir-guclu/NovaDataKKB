# MIA Rate-Limit Observations

## Date
2026-09-12

No real 429 response was observed during the current manual integration tests.

Because the provider quota / requests-per-minute limit is not documented in the available task information, the implementation does not assume a specific numeric quota.

## Retry Policy
`KloudeksProvider` retries `RateLimitError` with exponential backoff:

1. 2 seconds
2. 4 seconds
3. 8 seconds

After the third retry delay, the next 429 is propagated to the caller.

## Validation
The retry behavior was verified with a simulated 429 test in:

`backend/tests/core/test_kloudeks_rate_limit_retry.py`

The test confirms four total attempts and sleep intervals `[2, 4, 8]`.

## Live Observation
Chat, native tool-calling, embedding and OCR requests completed successfully during integration testing without an observed rate-limit response.
