# MIA/Qwen Tool-Calling Test Result

## Date
2026-09-12

## Model
`kkbhackathon2026/Qwen3.8-27B`

## Endpoint
`https://mia.csp.kloudeks.com/v1`

## Result
Native OpenAI-style function/tool calling is supported.

Three empirical cases were tested:

1. Simple scalar parameter (`get_weather`)
2. Lakehouse-style tool with arrays and filters (`query_lakehouse`)
3. Nested financial-analysis parameters (`compare_series`)

All three returned:

- `finish_reason = tool_calls`
- a non-empty `message.tool_calls`
- valid function names
- JSON-formatted function arguments

## Architectural Decision
The agent/provider will use the native OpenAI-compatible mechanism:

- `tools=[...]`
- `tool_choice="auto"`
- `message.tool_calls`

The JSON-prompt fallback described in the task is not required.

## Observation
The model invented a placeholder table name (`housing_loan_rates`) in the synthetic Lakehouse test. This does not indicate a tool-calling protocol failure. Real tool execution must validate table/parameter values against the actual Tool Registry and Lakehouse catalog.
