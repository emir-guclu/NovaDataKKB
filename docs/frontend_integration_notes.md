# Frontend Integration Notes

## Scope
Updated Phase C is validated locally with Docker. Railway/cloud deploy acceptance and the former 110s client-timeout requirement were removed from scope.

## Integration
Frontend uses `NEXT_PUBLIC_API_BASE_URL` (default `http://localhost:8000`), first calling `POST /api/v1/ask/stream`. Only stream-transport failures may fall back to `POST /api/v1/ask`; validation, HTTP and runtime errors are not re-sent.

## Live Agent Activity
Safe SSE events from the backend `on_event` flow are mapped to user-facing status text. Full prompts, message history and raw tool payloads are not exposed.

Mapped tools include `series_catalog_search`, `evds_data_service`, `lakehouse_query`, `change_detection`, `anomaly_detection`, `causality_check`, `web_search`, and `web_url_reader`. The UI shows a live activity card, completed steps with a check mark, and a pulsing active step. Only high-level operational status is shown; hidden chain-of-thought is not exposed.

## Chat UX
While a response is pending, the input and send button are disabled, Enter cannot enqueue another request, `handleSend` has an `isLoading` guard, and a localized busy placeholder is shown.

The chat auto-scrolls when messages or live status change. Messages are restored from `sessionStorage`; manual acceptance confirmed F5 restores the conversation and moves to the latest message.

Live activity and errors are localized in Turkish and English.

## Error Handling
The frontend distinguishes HTTP 422 validation errors, general HTTP errors, backend runtime errors, network errors, stream termination, and unknown errors.

## Validation
- Backend: `251 passed, 1 warning`
- Frontend: `npm run build` -> PASS
- Manual: live activity, input lock, F5 auto-scroll, TR/EN activity, HTTP 422, network error, and recovery flow -> PASS
