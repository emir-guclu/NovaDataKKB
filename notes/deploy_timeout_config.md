# Deploy Timeout Configuration

## Selected Demo Platform

Railway is the selected PaaS target for the demo / intermediate deployment stage.

## Railway Request Timeout Behavior

Railway does not expose a separate per-service "120 second proxy timeout" setting that must be manually increased.

According to Railway public networking limits:

- HTTP requests with no data transferred are closed after 5 minutes (300 seconds).
- HTTP requests that keep transferring data may run for up to 15 minutes.
- WebSocket connections are exempt from these HTTP duration limits.

For NOVA, the existing Railway platform limit is therefore already greater than the required 120-second deployment safety margin.

## NOVA Application-Side Timeout Hierarchy

The backend enforces its own stricter timeout limits so that the application returns a controlled error before Railway terminates the request.

| Layer | Timeout |
| --- | ---: |
| Railway no-data HTTP limit | 300 s |
| NOVA `/api/v1/ask` hard timeout | 100 s |
| EVDS HTTP request | 75 s |
| MIA / OpenAI-compatible HTTP request | 60 s |
| `web_url_reader` HTTP / Playwright | 15 s |
| DDGS `web_search` | 5 s |

This preserves the synchronous API contract while preventing a single network call from waiting indefinitely.

## Runtime Configuration

The API hard timeout defaults to:

REQUEST_HARD_TIMEOUT_SECONDS=100

It can be temporarily overridden through the environment for timeout testing.

Example:

REQUEST_HARD_TIMEOUT_SECONDS=5

After deployment testing, production must use `100`.

## Frontend / CORS Configuration

The production frontend origin is configured through:

FRONTEND_ORIGIN=https://<frontend-domain>

Until the production frontend domain is known, localhost development is allowed at:

http://localhost:3000

Wildcard CORS (`*`) is not used in production configuration.

## Deployment Note

The Railway service must expose the FastAPI application on `0.0.0.0` and use Railway's `PORT` environment variable when the deployment command is finalized.

## Verification Status

Local Faz B verification completed successfully:

- EVDS slow-success request completed in 18.72 seconds.
- Controlled application timeout returned in 5.02 seconds when REQUEST_HARD_TIMEOUT_SECONDS was temporarily set to 5.
- Production/default REQUEST_HARD_TIMEOUT_SECONDS remains 100.

A deployed slow-request test must still be run after the Railway service is created.
